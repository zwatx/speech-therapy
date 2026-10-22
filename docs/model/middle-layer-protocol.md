# Fixed middle-layer acoustic representation

Declared September 27, 2026, before real intermediate features are extracted.
Test one fixed representation hypothesis: frame-normalized block-12 outputs from
the pinned phonetic encoder, versus freshly extracted final outputs from the
same forward pass. No layer grid, learned layer mixture, PCA variants or seed
search follows from the outcomes of this study.

Layerwise speech research motivates this hypothesis but does not establish that
layer 12 is optimal for this checkpoint or children's pronunciation:
[Pasad et al. 2021](https://arxiv.org/abs/2107.04734) and
[Pasad et al. 2022](https://arxiv.org/abs/2211.03929).
The structural midpoint of 24 blocks is chosen before feature extraction.

## Frozen extraction

Use the 9,891 expanded child positions from all 1,040 recordings / 52 children
ages 6–12, all 23 supported consonants. Inherit row identities, source audio,
frame counts and half-open estimated pooling windows from the existing expanded
position-feature plan. Do not read author-test audio, add labels, exclude clips
for quality or use YAMNet decisions. Audio is existing permitted development data.

Encoder: `facebook/wav2vec2-lv-60-espeak-cv-ft`, revision
`ae45363bf3413b374fecd9dc8bc1df0e24c3b7f4`. Verify the four original model-file
SHA-256 bindings, including `pytorch_model.bin` (not safetensors), before loading
and after extraction. Use float32, eager attention, eval mode, disabled gradients,
one unpadded clip per call, original normalized 16-kHz feature extractor and its
attention mask. No encoder fitting.

The installed Transformers 4.57.6 implementation and an actual synthetic probe
established stable-layer-norm semantics: hidden state 12 equals the output of
block 12 before the final encoder normalization; state 24 exactly equals
`last_hidden_state` after that final normalization. Assert 25 states, shape and
finite values, state-24 equality and block-12 hook equality during extraction.

For layer 12, apply parameter-free per-frame LayerNorm across 1,024 channels,
with the model's configured epsilon and no learned affine parameters, **before**
pooling. This scaling is part of the declared hypothesis: it is not a comparison
of two unmodified layers. Layer 24 uses the model's existing learned final norm.
For both families reuse the original pooling: NumPy mean in float64 over each
fixed window, cast to float32. Keep only pooled 1,024-dimensional vectors.

Use the 13 original cached CTC scalars unchanged in both families. They originate
from a separately quantized alignment model; recomputing them with this encoder
would change the experiment. No new alignment, probability calibration or
relabeling. Extracting all frozen features upfront is label-free; PCA and head
normalization remain fit-only.

The extractor receives an audio/window/identity manifest and reference features,
not rating votes. Preserve a complete one-to-one global-row mapping in cached
row order. Hash all outputs and source inputs, record environment and timing,
and freeze features before any head training.

## Numerical and resource gates

Start on the Mac with the existing Torch 2.8.0 / Transformers 4.57.6 / NumPy 2.2.6
environment, two CPU threads and deterministic algorithms. Check the first and
longest child recordings before the full run: fresh layer-24 pooled vectors must
have maximum absolute difference <=1e-5 from the cached vectors. The first clip
must reproduce both representations exactly at the end of extraction. Every
clip must match its audio hash, sample count, frame count and row/window binding.
Errors stop the experiment and are not speech-rejection decisions.

Measure the first 20 ordinary clips. Continue locally if their projected total
extraction time is <=45 minutes. Otherwise stop after preserving those label-free
timings; a separately reviewed Colab controller may extract both families in one
T4 runtime with a maximum of five existing compute units and 90 minutes including
setup. That fallback requires declared CUDA parity gates and environment binding
before allocation; this protocol alone does not authorize silently mixing local
and CUDA features. No purchases. A runtime failure does not trigger blind retries.

One code-defect correction is allowed only after independent identification and
a new source/plan declaration. No gate relaxation or outcome-driven rerun.

## Matched heads and comparisons

Two families: compact-L12 and compact-L24fresh. Use the unchanged expanded
child-only 25 speaker-fold × word-group cells, expanded inner fitting rows,
original selection rows in original order, and added validation rows only in
fresh refits. All 50 inner fits are frozen before 50 fresh refits; all refits are
frozen before the outer predictions. Original outer support is 5,654 positions
from 1,037 recordings / 52 children. These reused development cells are not a
new independent confirmation set.

Reuse `lexical_compact/core.py`: fit-only PCA16 of centered raw pooled features,
no column scaling before PCA, no whitening, deterministic eigenvector sign and
existing rank guard; concatenate 13 cached scalars, then fit-only normalization.
Seed 7, width 128, dropout 0.1, AdamW learning rate 0.0003, weight decay 0.01,
batch 64, norm clipping 5, CPU two threads. Select by original five-vote NLL,
maximum 100 epochs, patience 15, improvement >1e-7, no epoch-zero candidate.
Refit for the selected epoch count. Reuse the same frozen child scalar heads
and original outer predictions for both fixed equal-weight mixtures, after
binding and replay verification. No mixture-weight search.

Primary comparison: L12 mixture versus fresh-L24 mixture. Require pooled NLL
improvement >1e-7, every speaker-fold NLL nonworse within 1e-7, and nonworse
macro-phone NLL, Brier, rating-0 AP and below-2 AP within 1e-7. Co-condition:
compact-L12 pooled NLL improves over compact-L24fresh by >1e-7. Replacement also
requires the same six-part screen versus the retained mixture. Separately report
the stronger material target of at least 5% relative pooled NLL improvement and
0.01 absolute rating-0 AP improvement. Passing a directional screen alone does
not fulfill the overarching quality goal.

Report fresh-L24 versus retained as an implementation/numerical control, not a
statistical noise floor. Small floating-point changes can alter optimization
trajectories. Include per-age/phone/child support, metrics and fold changes,
fit-only PCA explained variance and largest-channel variance share. A fixed-seed
child-cluster bootstrap may be descriptive only; it cannot override the screens.

If primary or co-condition fails, close this fixed normalized-middle-layer /
mean-pooling / PCA16 recipe without trying other layers, norms, ranks or seeds.
Failure does not show that middle layers contain no useful information. A pass
is a candidate for separately declared confirmation, not clinical validation or
permission to enable learner feedback. Source and artifact reviews are required.
The current usable research package remains retained until stronger evidence
supports a replacement.
