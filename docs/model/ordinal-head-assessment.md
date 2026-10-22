# Ordinal rating head: defer this comparison

September 26, 2026. Decision memo only: **no ordinal model was implemented or
trained**, and no new label outcomes were inspected to choose configurations.
The current campaign will finish its declared experiments before adding another
architecture comparison.

The potential hypothesis is narrow: **a proportional-odds output constraint
improves clean corpus-rating log loss relative to categorical softmax, using
the same features and fitting data.** That is a defensible future question.
Twenty full-data fits would not establish data efficiency; that claim needs
matched learning curves over smaller, speaker-grouped training samples.

## Why ordering is plausible but insufficient

SpeechOcean's rubric distinguishes incorrect/missing production (0), otherwise
acceptable production with heavy accent (1), and correct production (2).
These are ordered source judgments, not three clinical SSD severity grades.
The [authors' rubric](https://github.com/jimbozhang/speechocean762#the-scoring-metric)
does not establish a single acoustic severity dimension.

For a phone-conditioned latent quality `q` and phone-specific ordered thresholds
`b0 < b1`, a cumulative-logit head would use:

```
P(Y = 0) = sigmoid(b0 - q)
P(Y < 2) = sigmoid(b1 - q)
P(Y = 1) = P(Y < 2) - P(Y = 0)
P(Y = 2) = 1 - P(Y < 2)
```

This [proportional-odds model](https://academic.oup.com/jrsssb/article/42/2/109/7027621)
imposes more than category order. **Within each phone, rating-0 and below-2
probabilities must rank every example identically.** Their measured AUROCs can
still differ because the two event labels differ. The constant threshold gap
also restricts how class-1 mass and rater disagreement can vary across examples.
Incorrect/missing sounds and acceptable accented productions may depend on
different acoustic evidence. That concern is a scientific inference from the
model and rubric, not a newly measured corpus result.

Sparse middle-class ratings can leave phone-specific threshold gaps poorly
identified or nearly collapsed. Ordered thresholds prevent invalid negative
probabilities; they do not create support. Location shifts between the latent
and thresholds are also redundant, so learned thresholds must not be presented
as interpretable clinical cutoffs.

## Capacity and a fair future comparison

The current target-plus-scalar head has 1,037 inputs, 128-dimensional acoustic
and phone representations, a 128-unit hidden layer, and 169,219 parameters.
Replacing its final 387-parameter three-way linear layer with a 129-parameter
quality layer plus 48 threshold parameters gives 169,009 parameters: **210
fewer, approximately 0.12%**. This calculation retains the fixed 24-ID inventory
with ZH unsupported. The main experimental change is the constrained probability
family, not a substantial reduction in model size. The architecture is recorded
in [multiphone_models.py](../../research/audio-head/multiphone_models.py) and the
[frozen head recipe](../../research/audio-head/experiments/multiphone-phonetic-heads-v1.json).

A future controlled study should use fresh heads, identical initial shared-body
tensors, fixed threshold initialization, the same unweighted five-rater
categorical NLL, fit-only normalization, and matched batching/stopping. Preserve
all 23 eligible phones, both fitting populations, the same five inner folds and
the two already declared learning rates. Retain class-1 likelihood, proper
scores, both ranking events and every failure; do not select another link or
threshold-sharing scheme after observing results.

An arbitrary trained softmax distribution cannot generally be converted into
an equivalent one-latent initialization. A warm-start comparison would therefore
change initial predictions as well as architecture. If matching the archived
softmax initialization/RNG contract cannot be demonstrated, fit fresh matched
softmax controls too; the comparison then exceeds 20 new fits. None of this
supplies ages 2–5, verified SSD examples, produced-phone labels, or independent
evaluation. Completing the current bounded studies and the annotation handoff
is the stronger next action for Cadence.
