# Ordinal (proportional-odds) rating head: fixed comparison protocol

**Pre-execution protocol, 2026-09-30.** No ordinal model has been implemented, trained or scored when writing this. It tests the narrow question left open in the [deferral memo](ordinal-head-assessment.md), using the same features, fitting data, recipe and evaluation as the [M6/M10 comparison](child-acoustic-heads-result-20260929.md).

This is **development evidence** on extensively reused data, not fresh validation. The five expert votes are observed ratings, not produced-phone truth. No clinical claim, learner judgment, threshold, filter or retained-bundle change follows from any result.

## Question

On the retained model's own features and fitting data, does replacing each head's categorical softmax output with a proportional-odds output improve prediction of the five expert ratings on the original outer child positions? Rare-error ranking (rating-0 and below-2 AP) is reported alongside.

## Model change (the only change)

Each head keeps `MeanPoolPhoneRatingHead` unchanged: the phone embedding, the acoustic projection, and the classifier up to and including dropout. Only the final `Linear(128, 3)` is replaced by:

- **Latent quality score.** `q = Linear(128, 1)(h)`.
- **Per-phone thresholds** (24 IDs): `b0[phone]` and `gap[phone]`, with `b1 = b0 + softplus(gap)`, so `b0 < b1` always.
- **Class log-probabilities** (all in float32):
  - `log P0 = logsigmoid(b0 − q)`
  - `log P2 = logsigmoid(q − b1)`
  - `log P1 = logsigmoid(b1 − q) + logsigmoid(q − b0) + log(−expm1(−softplus(gap)))`

  The last line uses the exact identity σ(a) − σ(c) = σ(a)·σ(−c)·(1 − e^{−(a−c)}) for a > c.

The head returns these three log-probabilities in place of logits. The unchanged training cores then apply `log_softmax`, which equals the log-probabilities up to float rounding and renormalizes exactly in float64 for scoring. **Training loss, optimizer, batching, selection, early stopping and prediction code stay unchanged.**

Initialization:

- **Body.** The head is first built exactly as the softmax control, consuming the same global RNG draws under seed 7. So the body's initial tensors and the global RNG state at the start of training (dropout masks) are identical to the control's. The discarded `Linear(128, 3)` is created and dropped so these draws match.
- **Quality layer.** Weight and bias are drawn uniform(−1/√128, +1/√128), PyTorch's default `Linear` bound, from a **separate** `torch.Generator` seeded 7. This never touches the global stream.
- **Thresholds.** Fixed for every phone: `b0 = −1`, and `gap = log(e² − 1)` so that `b1 = +1`.

The unchanged AdamW weight decay (.01) and global gradient clip (norm 5) act on the new quality and threshold parameters, just as they act on the softmax control's output weights and biases. Decay pulls the thresholds and gap toward 0 by about 3e-6 relative per step (pre-execution review note).

This is the only link, threshold sharing and initialization evaluated. No alternative link, sharing scheme, initialization or learning rate is searched.

Parameter change: the 387-parameter `Linear(128, 3)` becomes a 129-parameter quality layer plus 48 threshold parameters.

## Fitting (unchanged)

Both families of the retained mixture are refit in ordinal form:

- **Scalar family (13 CTC scalars):** `lexical_heads/core.py`.
- **Compact family** (PCA16 of the retained 1,024-dimensional target features + 13 scalars): `lexical_compact/core.py`.

For the 25 child-only speaker-fold × word-group cells in the [prepared plan](../../work/child-acoustic-comparison-prep-20260928/comparison-plan.json), the fitting follows the M6/M10 procedure:

- **Rows.** The same fit, selection and refit rows, in original order.
- **Transforms.** Normalization and PCA are fit only on the fit rows.
- **Epoch selection.** Each job selects its own epoch from 1..100 on the original selection rows only (patience 15, minimum improvement 1e-7). It then refits on the refit rows at that epoch.
- **Recipe.** Seed 7, CPU, 2 threads.

Features are the retained expanded target and scalar rows at the manifest row indices. These are the byte-identical features already verified in the M6/M10 control gate.

That makes 2 families × 25 cells × (inner + refit) = **100 ordinal fits**.

**The head is swapped by runtime substitution in the worker only.** Setting `MeanPoolPhoneRatingHead` in both core modules to the ordinal class leaves frozen files unedited. The same substitution applies to replay, so saved checkpoints reload into the same class.

## Control gate (before any ordinal outer prediction)

The worker first refits the 50 cached softmax control jobs for **both** families on the same feature geometry: 100 fits, used for verification only. Selected epochs must equal the frozen ones, refit weights must be tensor-equal, and predictions under the frozen all-outer-row batching must be exact.

Any failure stops the experiment. Controls used in evaluation are the **cached frozen outer artifacts only**; they are never relearned.

## Arms and comparisons

| Arm | Definition |
| --- | --- |
| Scalar (cached) | cached `child-only-scalars` outer predictions |
| **Retained** (cached) | `logaddexp(log scalar, log compact) − log 2`, cached softmax heads |
| **Ordinal mixture** | the same mixture of ordinal scalar and ordinal compact |
| Ordinal scalar / ordinal compact | each ordinal family alone (secondary) |

- **Primary contrast:** ordinal mixture − retained.
- **Secondary contrasts:** ordinal compact − cached compact, and ordinal scalar − cached scalar.

## Evaluation (fixed, reuses the M6/M10 evaluator's estimands)

- **Primary population:** the 5,654 original outer child positions (52 children, 23 consonants). The 4,237 added positions are descriptive only.
- **Metrics:** pooled five-vote NLL (primary), phone-macro NLL, pooled per-rater Brier, tie-aware weighted rating-0 AP and below-2 AP. All use the frozen `rating_temperature` summary path.
- **Bootstrap:** 2,000 paired whole-child resamples within the five original speaker folds, seed 20260928, NumPy linear 2.5/97.5 percentiles. Undefined replicates are counted and never redrawn.
- **Leave-one-child-out:** every child is deleted in turn.
- **Breakdowns:** per phone, fold, cell and child.
- **Batching effect:** new arms predict child rows in 64-row batches. The effect on every metric is measured by rebuilding the cached arms (scalar, compact and retained) from the control arm's child-batch predictions. The screen, which depends only on retained, is then recomputed with them.

**Advancement screen** (ordinal mixture vs retained). The ordinal head becomes a candidate for separately declared fresh validation only if:

- NLL improves by at least .005 nats/position;
- the bootstrap upper endpoint is below zero;
- every child deletion keeps a favorable sign; and
- phone-macro NLL worsens by at most .005, per-rater Brier by at most .002, and each AP drops by at most .02 absolute.

If more than 5% of bootstrap replicates are undefined for a guard, that guard is labeled unstable/descriptive and the point screen is unchanged. These margins are the same practical judgments used before, not power-derived.

Report every gain and regression, including rare-event AP changes, even if the screen fails. The constraint forces rating-0 and below-2 scores to rank examples identically within a phone. Report whether that visibly costs ranking quality for either event.

## Verification and review

- **Tests:** synthetic unit tests of the ordinal head. They cover the probability identity, normalization, the ordering of thresholds, float32 finiteness at extreme q, identical body tensors and global RNG state versus the softmax control, and strict-load replay.
- **Lineage:** worker lineage and control-gate checks, following the M6/M10 worker.
- **Declaration:** binds sources, inputs, the protocol and the runtime.
- **Reviews:** Fable 5.1 reviews the implementation before declaration and the result before it is reported.
- **Failures:** retained, never rerun silently.

## Limits

Five expert votes on reused author-training data from 52 children cannot establish clinical meaning, produced-phone accuracy or generalization. The ages 8 and 10 fitting groups each have two children. A pass only prioritizes fresh validation, which currently lacks accessible data. A failure closes this exact link, sharing and initialization only.
