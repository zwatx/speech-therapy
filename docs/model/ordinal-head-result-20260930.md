# Ordinal (proportional-odds) rating head: result

**The proportional-odds head was clearly worse than the retained softmax model, and it fails the fixed screen.** It was worse on every primary metric except below-2 AP, which was roughly unchanged. Its largest loss was in rating-0 ranking, the rare-error event the deferral memo flagged. This closes this exact link, threshold sharing and initialization ([protocol](ordinal-head-protocol-20260930.md)). The retained research bundle is unchanged.

This is development evidence on extensively reused data, not fresh validation. The five expert votes are observed ratings, not produced-phone truth.

## Primary result

The primary population is 5,654 original outer positions from 52 children, across all 23 consonants.

| Arm | NLL | Phone-macro NLL | Per-rater Brier | Rating-0 AP | Below-2 AP |
| --- | ---: | ---: | ---: | ---: | ---: |
| Scalar (cached softmax) | .18012 | .19311 | .08161 | .08843 | .16021 |
| Compact (cached softmax) | .17923 | .19022 | .08045 | .08897 | .17391 |
| **Retained** (cached mixture) | **.17746** | **.18910** | **.08037** | **.09208** | .16988 |
| Ordinal scalar | .19553 | .20964 | .08358 | .06701 | .16040 |
| Ordinal compact | .19501 | .20724 | .08254 | .06031 | .16523 |
| Ordinal mixture | .19237 | .20481 | .08225 | .06573 | .16643 |

| Contrast | NLL Δ | 95% bootstrap | Rating-0 AP Δ | 95% bootstrap | Leave-one-child-out favorable |
| --- | ---: | --- | ---: | --- | ---: |
| **Ordinal − retained** | **+.01491** | [+.0097, +.0217] | **−.02634** | [−.0390, −.0141] | 0 / 52 |
| Ordinal compact − compact | +.01578 | [+.0104, +.0226] | −.02866 | [−.0423, −.0155] | 0 / 52 |
| Ordinal scalar − scalar | +.01540 | [+.0098, +.0224] | −.02143 | [−.0363, −.0091] | 0 / 52 |

The bootstrap uses 2,000 paired child resamples within the five speaker folds (9/10/14/9/10 children). No replicate was undefined.

- **Screen.**
  - Failed: the NLL gain (≥ .005 needed; the ordinal mixture was worse by .0149), the bootstrap upper endpoint, every child-deletion sign (deletions ranged +.0127 to +.0154), the phone-macro NLL guard (+.0157 > .005), and the rating-0 AP guard (−.026 exceeds the .02 allowance).
  - Passed: the Brier guard (+.0019 ≤ .002) and the below-2 AP guard (−.0035).
- **Consistency.**
  - All five speaker folds are worse, from +.0074 to +.0219.
  - The ordinal head beat retained for only 6 of 52 children, and on only 2 of 23 consonants (DH, TH).
  - The largest per-phone losses were JH (+.066), CH (+.049), R (+.046), L (+.039) and N (+.031).
  - Both families lose on their own by similar amounts, so the loss is not an artifact of mixing.
- **Added population (descriptive, 4,237 positions).** It was also worse: ordinal − retained NLL was +.0136.

## Interpretation (limited)

This matches the concern in the [deferral memo](ordinal-head-assessment.md). A single latent score forces rating-0 and below-2 scores to rank examples identically within each consonant. Rating-0 AP fell by about 29% relative, while below-2 AP was roughly unchanged. That pattern is consistent with rating-0 (incorrect or missing) and rating-1 (acceptable but accented) depending on different evidence, which a one-dimensional latent cannot represent. It is consistent with that account, not proof of it; other link functions, shared thresholds or initializations were deliberately not searched and are not reopened by this result.

## Verification

- **Control gate, both families.**
  - Replay: 50/50 control jobs had byte-identical features and replayed exactly under the frozen batching. This is the first such check for the scalar family.
  - Refits: all 50 softmax jobs matched the frozen controls exactly in selected epochs, refit weights and predictions.
  - The ordinal outer predictions were gated on this pass.
- **Fit.** The ordinal head shares identical body initialization and global RNG state with the softmax control, verified by tests. `skip_init` fixed a pre-review bug in which plain `nn.Linear` construction consumed global RNG draws. Checkpoints prove their head type from their state-dict keys.
- **Evaluator.**
  - It re-verified the lineage of all 100 fits per arm, and replayed all 50 outer predictions per arm (ordinal and control) from their refit checkpoints.
  - It asserted that the lean bootstrap metrics equal the frozen summary path within 1e-12.
  - Batching effect: at most 4.5e-11 on any metric, and no screen check changed.
- **Execution.** 100 ordinal fits and 100 verification-only control fits ran on the Mac CPU (seed 7, 2 threads). From file timestamps: control fit started 04:04:53Z and its outer freeze was written 04:07:03Z; ordinal fit started 04:07:23Z and its outer freeze was written 04:10:22Z. No Colab or audio was involved.
- **Tests.** 15 synthetic tests pass. They cover the head math and extremes, RNG and body parity, strict reload, scoped substitution and its restoration, real tiny fits through both cores with lineage checks, and the screen.
- **Reviews.** Fable 5.1's pre-execution review (`claude-fable-5-1` confirmed from usage metadata) returned CLEAR with notes. Two of those notes were added to the protocol before declaration, and one parity assertion was restored.

## Artifacts

All paths are under `work/ordinal-heads-20260930/`.

| Artifact | Path | SHA-256 |
| --- | --- | --- |
| Declaration | `v1/declaration.json` | `24331ff2cc72e4375cada14a815a651e0ffc8ad0f56cef86322e68879af14063` |
| Control replay | `v1/control-replay.json` | `b15a6eecec2802c649220cdee5196f74380ab16aa8ae82daf313d1bd386b0c2f` |
| Control refit check | `v1/control-refit-check.json` | `3dc053b70ba423efbc92c79c8b16e8cdee6bade7287db0888e5df5f181de152d` |
| Evaluation | `v1/evaluation/report.json` | `88fb7f04ed27a680ce6119545245743d1f5f0783a87a8d5beb83e0c7db9c7e64` |
| Reviews | `review-v1.md` (pre-execution CLEAR), `result-review.md` | |

The result review (Fable 5.1, `claude-fable-5-1`) confirmed every number against the evaluation JSON. It found five wording or provenance corrections, all applied here: the replay count, the timing source, the review file, the gate hashes and the motive wording.
