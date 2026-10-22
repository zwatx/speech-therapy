# Retained ages 6–12 bundle: fixed cached-noise sensitivity

September 29, 2026. Pre-execution protocol. This is a descriptive replay of a
previously consumed synthetic condition on author-training data, not a fresh
validation, replication of accuracy, model comparison or improvement screen.
No new model predictions have been inspected for this replay when writing it.
Pre-execution corrections from the separate review made explicit the clean
source, exact feature gate and actual-age call grouping; no predictions exist.

## Question and fixed scope

How much do the unchanged full-fit ages 6–12 scalar/PCA16 mixture probabilities
move between existing clean features and the existing 20 dB Gaussian-noise
features? The retained bundle was fitted on these speakers and recordings.
The earlier consistency studies already consumed this condition and data;
this check adds sensitivity evidence for the newer full-fit bundle only.

Use the caller-pinned retained bundle manifest SHA-256
`bc62f1e4f1727379161d0f3f7d8e6074e645e7578b5c25661fd9da53e4fde1bf`.
Do not alter weights, projection, normalization, mixture weights, target IDs,
loader batching or the eligibility flags. Group rows by their recorded age,
calling the loader once per actual age in increasing age order; preserve row
order within each group and restore the declared overall order afterward. Use
identical grouping and batch boundaries for clean/noisy calls. Use the existing
feature-only loader serially on CPU with two threads and the verified local Python/PyTorch/NumPy
environment. Bind loader/model/worker/test/protocol sources and all bundle files.

Use every age-eligible row (6 <= recorded age < 13) of the completed legacy
consistency-feature extension, expected 5,654 positions, in its declared row
order. Join each row to the expanded fitting cohort by its complete occurrence
identity; require exact agreement on speaker, age, clip, canonical phone,
target ID and word/phone indices. Require membership in the retained bundle's
fitting population. Do not select by labels, confidence, noise movement, phone
support or previous model outcomes. Missing, duplicate, reordered or mismatched
rows stop the entire run; they are not excluded or replaced. Save the exact
selection and deduplicated speaker/clip/age/phone support before prediction.

The legacy cache has fewer sound positions than the expanded 9,891-row fitting
population. Repeated occurrences outside that cache are not represented.
The metadata join identifies 1,037 of 1,040 fitting recordings, 52 children and
23 consonants. Three fitting recordings have no eligible legacy-cache target.
Never describe this as coverage of all fitting positions. Clean probabilities
on these fitting features were already measured during the bundle export;
only this bundle's noisy predictions are new.

## Existing feature provenance

Use the expanded bundle fitting matrices for clean features and the completed
consistency extension matrices for noisy features. Before any prediction,
compare EVERY joined clean row with the original consistency study's clean
features: require exact array equality for all 1,024 target columns and all
13 scalar columns (no tolerance or fallback). Confirm scalar ordering and
occurrence/canonical-window identity from bound metadata. A mismatch stops the
study before prediction, with no row substitution or loosened gate. This gate
prevents extractor changes from being mistaken for noise effects.

Reuse the completed consistency extension's row-index maps, manifest and
per-unit provenance without changing identities.
Rehash the declared artifacts and check the clean/noisy matrices have finite
float32 [N,1037] values, ordered target IDs and exact row-to-unit joins. Bind the
original extraction declarations and feature lineage. The original transform
was source-hash-seeded Gaussian noise at 20 dB whole-waveform SNR, common
attenuation when needed and PCM16 quantization. It recomputed posterior
sequences, 13 scalars, estimated windows and 1,024-dimensional pooled features.
No waveform is regenerated, downloaded or forwarded through an encoder here.
The original transform and extraction verification remain inherited evidence,
not newly independent acoustic verification.

Before any prediction, write a fresh immutable declaration with timestamp,
all file paths/SHA-256 bindings, source hashes, runtime identity, exact selected
rows, feature provenance, output destination and this protocol. A separate
reviewer must clear scientific and implementation blockers first. After
writing the declaration, require its caller-supplied SHA-256 for execution.
Recheck inputs before and after inference. No overwrite or implicit restart;
record incomplete/failure state durably and stop rather than repairing a run.
A software mismatch stops before predictions. Any material pre-execution
correction requires review and a new declaration before results exist.

## Fixed reporting and verification

Save both three-class probability arrays and row identities. Compute each
row's total variation as half the sum of absolute class-probability differences,
class order as corpus rating 0,1,2; expected rating as p1 + 2*p2,
signed noisy-minus-clean expected-rating drift,
absolute drift, and argmax change (NumPy's first-index tie behavior). Retain
all rows, counting each position once, and compute position-weighted mean/max TV, mean signed and absolute
expected-rating drift, argmax-change count/denominator, and clean/noisy mean
class probabilities. Present the same quantities for every phone, recorded age,
speaker and recording. Do not select the worst case for another experiment or
suppress negative or zero changes. No confidence intervals or hypothesis test.

Synthetic tests must cover exact metric arithmetic, correct joins, duplicate,
missing and mismatched identities, and corrupted pinned inputs. A separate
process must verify hashes, row order, normalization, saved probabilities and
reconstruct all summaries without new model inference. A parent audit checks
summary arithmetic separately. Retain failures and report any verification
that does not complete before the user-requested safe pause at 15:16 Chicago.

No human rating is used as transformed-audio truth or scored here. Smaller
movement can preserve mistakes or reflect lost acoustic distinctions. This
one synthetic condition on fitted, previously explored data does not establish
pronunciation correctness, robustness to physical microphones, independent
speaker/word generalization, clinical validity, speech retention or nonspeech
rejection. No threshold, filter, model promotion, app or learner-feedback change
follows. The nonspeech Part A study stays closed; Part B still needs PERCEPT-R
access. Audio, existing features, derived probabilities and reports remain local
noncommercial research assets.
