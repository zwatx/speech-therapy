# Expanded-audio Colab pilot

Declared before GPU allocation or outcome inspection, September 27, 2026.
This tests whether updating the last acoustic encoder layer helps a matched
rating predictor on expanded canonical occurrences under complete-utterance
word exclusions. It is a bounded development pilot, not a new clinical task.

## Fixed data and comparison

Use existing child-only speaker fold 0 / word group 0, chosen by index before
training. The pinned expanded-data plan supplies 1,997 fitting positions from
38 children and 150 original checkpoint-selection positions from five different
children. Both retain all 23 supported consonants. The later comparison contains
209 original positions from nine other children; JH has no comparison positions
in this cell and must appear with zero support. All children are ages 6–12.
The same held-out word group is absent from every complete fitting/selection
utterance. This does not make these historically reused data an untouched test.

Only the 372 selected public author-training recordings are packaged. Labels
remain five subjective 0/1/2 ratings per occurrence. Repeated consonants retain
distinct occurrence IDs and estimated windows. No patient data, author-test
audio, credentials or unrestricted workspace archive is uploaded.

Fit normalization and a 128-wide target-conditioned head on the 1,037 cached
features, using seed 17, AdamW, learning rate 0.0003, weight decay 0.01, batches
of 64, maximum 20 epochs and patience 4. Select by original-selection macro-phone
NLL with epoch zero eligible and earliest exact tie. Normalization uses fitting
rows only. This is a fresh matched pilot control, not the existing scalar/PCA
mixture and not a replacement portable bundle.

Load the exact pinned `facebook/wav2vec2-lv-60-espeak-cv-ft` revision
`ae45363bf3413b374fecd9dc8bc1df0e24c3b7f4`. Use float32 CUDA, eager attention,
one unpadded waveform, fixed original CTC windows/scalars and no encoder dropout,
augmentation or layer dropping. Check cached/raw features on the first and
longest fitting clip before continuation: maximum absolute feature difference
below 0.005 and probability difference below 0.001. Record actual differences;
these tolerances are numerical sanity checks, not an exact backend parity claim.
All model comparisons use the same CUDA raw-audio baseline.

Retain three candidates:

1. Frozen encoder and selected cached head, evaluated through raw CUDA audio.
2. Head-only continuation for two epochs.
3. Matched head continuation plus only the final of 24 encoder layers updated
   at learning rate 0.000001, for two epochs.

Both continuation arms start from identical head/encoder parameters and RNG,
use the same clip order and four clips per update, and normalize soft-label NLL
by the number of target occurrences per update. Head learning rate is 0.0003;
weight decay is 0.01 and gradient norm cap is 1. Epoch zero remains eligible.
Save the last and selected states, histories, gradient/update evidence and
selection predictions. Verify that frozen encoder parameters do not change.

The local packaging step already reads held-out metadata, labels and support
counts without model inference or outcome selection. In the remote trainer,
freeze all three selected checkpoint hashes before parsing held-out labels or
decoding held-out audio. Restore checkpoints for evaluation. Save aligned
probabilities/log-probabilities and votes, with NLL, macro-phone NLL, Brier,
rating-0 and below-2 AP and all 23 phone support cells. Macro NLL averages
only represented phones (22 in this outer cell); JH has zero support and null
NLL, never a fabricated zero loss. AP may be calculated by
the local independent report after the raw predictions return. Preserve empty
classes explicitly; no missing-label imputation or synthetic error labels.

The primary contrast is adapted versus head-only; adapted versus frozen is
also required. Continue this approach only if child held-out NLL improves and
macro NLL/Brier do not worsen beyond 1e-7, both event APs do not decrease beyond
1e-7 where defined, and the selected adaptation actually updated encoder
parameters. Missing event classes or failed execution cannot pass the screen.
Per-sound regressions remain visible. Also report the existing unweighted expanded
child scalar/PCA mixture on these identical original child positions as descriptive
context. Its seed and architecture differ; this is not a matched causal contrast
or a new selection rule. A passing single-cell screen justifies
broader replication, not promotion; a failure does not justify retrying seeds or
thresholds on these outcomes. Runtime feasibility is reported separately from
model-quality results. No automatic larger experiment is declared here.

## Compute, failure and verification

The user's latest authorization is **300 existing compute units total this
month across the work**, superseding 100. This pilot is capped at **5 units**,
including setup and evaluation. Request one T4; record actual GPU, account
balance and units/hour. Provision only after source/data review. Use a local
supervisor to enforce a conservative time allowance from the observed rate,
check usage, download the results and stop the named session in `finally`.
Training has its own deadline; the supervisor reserves time for transfer and
shutdown. No upgrade or purchase is authorized.

Record the actual CUDA/PyTorch/NumPy/Transformers environment; do not claim
bitwise equivalence to the Mac. Transformers 4.57.6 and NumPy 2.2.6 are pinned;
the supplied CUDA PyTorch runtime is recorded. Dependencies are isolated to
the new remote session. A source/data hash or parity failure stops the run.
Retain failures and partial logs; never turn incomplete work into a passing
comparison. An observation timeout alone does not authorize restarting a job.

Before allocation: source review and focused tests of repeated targets, invalid
labels/partitions/windows, scoring and selection. After execution: verify
downloaded bytes, selected checkpoint replay, frozen parameter invariants,
row/label alignment, locally recomputed metrics and actual session shutdown.
Review actual learning results without repeating a large audit framework.
Learner eligibility, clinical-use eligibility and promotion remain false.
