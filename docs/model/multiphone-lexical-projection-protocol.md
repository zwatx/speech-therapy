# Fixed supervised projection correction

This study tests one fit-only adjustment to the compact phonetic representation.
It starts from each frozen PCA16/scalar head, keeps all head weights, PCA center,
base basis and normalization fixed, and learns only a zero-initialized
1024×16 additive projection correction. It is a new adaptive development
comparison, not independent validation or proof that variance compression lost
rating information. All earlier outcomes, including failed consistency screens,
remain retained. No participant, phone, position or label is excluded.

## One fixed training recipe

Use the original 50 canonical lexical cells: both age regimes crossed with
five speaker folds and five whole-utterance word exclusions. Inner adaptation
starts from the corresponding previously selected inner PCA head and its
fit-only transform. Use only that cell's original inner-fit rows for gradients
and its original selection rows for epoch choice. Selection data has already
selected the starting head; this is explicitly reused development selection.

Compute the original PCA16 coordinates exactly as before in float64, then cast
to float32 and concatenate the unchanged 13 scalar features. Add
`float32((rawTarget - savedCenter) @ delta)` to only the first 16 coordinates.
The saved float32 normalization and frozen head operate as before. Delta starts
at exact zeros, preserving the original coordinates and requiring exact
probability/log/raw-output/NLL replay of the source selection predictions.
No new PCA decomposition or feature normalization is fitted. Delta is a free
linear correction, not constrained to remain orthogonal. Its parameter count
is 16,384; the prediction head stays in evaluation mode with dropout disabled.
Gradients flow through the frozen head to delta; head weights never update.

Fixed recipe: CPU, two threads, seed 7, batch size 64, AdamW learning rate
0.0001, weight decay 0.01, gradient norm clip 5, maximum 20 adaptation epochs,
patience 5, and minimum selection NLL improvement 1e-7. Training uses the original
equal-position five-rater negative log likelihood. Selection uses the same
per-rater NLL with stable unclipped logs. Epoch zero is an eligible checkpoint;
earlier epochs win ties. Save epoch-zero and every subsequent selection vector,
loss, permutation hash and update count, plus initial/best/last delta checkpoints,
optimizer and RNG state. There is no learning-rate, rank, seed or patience search.

Freeze all 50 inner results before any adaptation refit. Refit adaptation starts
from each original frozen refit PCA head/transform, resets delta to zero, and
uses exactly that cell's selected adaptation epoch count, including zero.
Gradients use the full original refit rows (inner-fit plus selection, with
speaker/word exclusions unchanged); no validation is used in this phase.
These are fresh projection corrections atop previously fresh-refitted source
heads, not newly refitted head weights. Freeze all 50 adaptation refits before
any new outer inference. A zero selected count preserves its source model.

## Evaluation and verification

For each outer cell, require exact zero-delta replay against the frozen compact
prediction before evaluating the selected correction. Preserve every original
outer row exactly once per regime, original five-vote counts and all 23 phones.
Retain all 25 cells, five speaker-fold summaries and pooled metrics, age and
word support, missing/undefined rare-class metrics and original fitting priors.

Primary comparison: corrected projection versus frozen compact. Use the existing
six-check screen: pooled child NLL improves by more than 1e-7; every speaker-fold
child NLL worsens by at most 1e-7; pooled child macro-phone NLL and Brier worsen
by at most 1e-7; pooled child rating-0 and below-2 AP decline by at most 1e-7.
Secondary comparisons use the same screen against scalar and the fixed mixture;
report original prior differences too. None authorizes clinical use or overrides
limitations of reused outcomes. No per-phone winner or new mixture is selected.

Declare recipe, code/tests/protocol, inputs and complete source checkpoint/phase
lineage before adaptation. Preserve source snapshots. Test zero-correction exact
parity, frozen-head gradients, deterministic update math, epoch-zero selection,
zero-epoch refit, invalid partitions and source changes. Independently review
source and actual artifacts, replay selected predictions, and reconstruct final
metrics offline. A failed stage leaves a failure receipt and completed-job list;
do not mutate the declaration or silently restart on a wait timeout.

All speech/data are the existing permitted author-training cohort. No author-test
access, new encoder/audio processing, external data acquisition, Colab allocation,
app changes, learner judgments or production model promotion are part of this
bounded study. GPU compute is unnecessary for these cached-feature updates.
