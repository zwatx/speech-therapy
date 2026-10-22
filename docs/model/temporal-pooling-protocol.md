# Fixed temporal partition of the existing alignment window

This is a new development experiment following the failed fixed-seed middle-layer replication. It tests whether preserving temporal position within the existing padded alignment window improves unfamiliar-speaker/word rating prediction. The same development participants and words have informed multiple experiments; a favorable result would require separate confirmation. Optimization seeds are not independent participant replications.

## Representation and extraction

Use the existing frozen final-layer encoder `facebook/wav2vec2-lv-60-espeak-cv-ft`, revision `ae45363bf3413b374fecd9dc8bc1df0e24c3b7f4`, with the checkpoint bytes bound by the original position-feature plan. Extract only the same 1,040 recordings from 52 children ages 6–12 and all 9,891 expanded supported positions. Preserve all 23 consonants, row identities and cached 13 alignment scalars. No author-test recordings, new labels, alignment changes or label-based extraction selection.

For each cached nonempty half-open interval `[s,e)` in a recording with `T` frames, use three half-open bins:

- Before: `[max(0,s-2),s)`.
- Interval: `[s,e)`.
- After: `[e,min(T,e+2))`.

These bins must partition the exact old padded pooling window. Average each bin's float32 final-layer vectors with float64 accumulation, then cast to float32 and concatenate in before/interval/after order, producing 3,072 values. An empty context bin receives the interval mean, while its recorded count stays zero. Save counts and the separately computed old padded mean. Preserve the original encoder normalization and preprocessing.

These are contextual encoder frames around an **estimated alignment interval**, not verified produced-phone boundaries. The cached alignment scalars and intervals came from a different quantized checkpoint; there is no claim that these features exactly contain its logits. Count-weighted bin means reconstruct each row's padded mean, but varying bin counts do not establish a single global linear nesting. PCA compression can discard useful information; the representation is a hypothesis, not an improvement by construction.

Before actual extraction, freeze protocol, source, runtime, checkpoint, audio and rating-free manifest bindings and obtain independent source review. Use the established deterministic Mac CPU environment, two threads and batch one for authoritative features. A separate reviewed hardware benchmark may compare Colab without substituting different features into this experiment.

Extraction validity requires:

1. Exact identity joins, valid interval/window bounds and complete unique recording/row coverage.
2. Float64 count-weighted reconstruction before casting within maximum absolute error `1e-10`; separately report the float32 persisted-bin reconstruction residual, without applying that float64 tolerance to rounded values.
3. The freshly extracted padded mean must equal the historical final-layer cache **bit exactly** for every child position. A mismatch stops control reuse and preserves diagnostics; no silent tolerance fallback, new control recipe or restart.
4. First and longest recording replays must be bit identical for all persisted outputs. Validate shapes, finite values, row order, counts, empty-bin inventory and all hashes.

## Matched model experiment

After independently reviewing extraction results, declare the training plan and independently review its source before fitting. Use exactly seeds **17, 29, 43** and all 25 existing speaker-fold × word-group cells per seed. Keep ordered fitting, selection, added-validation, refit and original-child outer membership unchanged. Evaluate all 5,654 original-child outer positions.

Fit centered PCA16 without whitening or column scaling on fitting rows only, then concatenate the same 13 scalars and apply the existing fit-only head normalization. The head input remains 29-dimensional. Reuse the unchanged unweighted five-vote categorical loss, hidden width 128, dropout .1, AdamW learning rate .0003/decay .01, batch 64, clip norm 5, maximum 100 inner epochs, patience 15 and improvement tolerance `1e-7`. Fresh refits use the selected epoch count. No epoch-zero candidate, bin/PCA/layer/seed search, age/phone gating, recalibration or across-seed ensemble.

The primary comparison is each temporal compact head mixed equally with its same-seed frozen scalar head versus the corresponding final-mean compact/scalar mixture. Compact-head NLL is a co-condition. Require exact feature/scalar, ordered membership and training-recipe compatibility before historical control reuse. Revalidate and replay all 150 frozen scalar/final controls. Previously reviewed same-runtime trainer parity probes may be reused only with exact source/runtime bindings and verified receipts; otherwise new prechosen probes require an amended declaration before fitting. Temporal and same-seed final compact initial model tensors must match.

Freeze all 75 inner fits, then all 75 fresh refits, then all 75 outer predictions. Incomplete phases cannot be evaluated. Integrity, source drift, runtime or control-parity failure invalidates execution rather than counting as a model-quality outcome. Preserve partial outputs and independently review corrections before any separately recorded restart. Old studies stay unchanged.

## Decision and reporting

Each seed must satisfy the same six-part primary screen: pooled mixture NLL change below `-1e-7`; every speaker-fold NLL change at most `1e-7`; macro-phone NLL and Brier changes at most `1e-7`; rating-0 and below-rating-2 average-precision changes at least `-1e-7`. Compact NLL must improve by more than `1e-7`. Undefined primary endpoints invalidate evaluation.

All three seeds must pass. Also fail the all-age guard if any age 6–12 has mixture NLL worsening by more than `1e-7` at all three seeds. Show smaller and less-consistent regressions. Separately report the stronger material target of at least 5% relative NLL improvement and +.01 rating-0 AP alongside the directional screen; a mean across seeds cannot rescue failure.

Report pooled metrics and deltas, all five folds, seven ages, 23 phones and 52 children with identical support; include rating-0 AP and macro NLL for age 6. Report all-seed subgroup NLL regressions, empty-bin counts, extraction/replay parity, and elapsed compute. PCA retained variance and squared component-loading share in each temporal block are descriptive fit-only diagnostics, not post hoc tuning criteria. They do not establish causal feature importance.

Require independent post-run review. A successful development screen permits designing separate confirmation, not replacing the packaged model or enabling learner judgments. Failure closes automatic replacement with this fixed recipe, not every temporal architecture. Neither outcome alone establishes the broader goal or clinical validity.

## Compute

The prior 1,040-recording extraction took about 206 seconds on the Mac; this is context, not a new measurement. The user authorized the existing monthly Colab allowance and requested attention to GPU speed. A separately frozen benchmark will compare a deterministic duration-spanning subset on Mac CPU and a T4, including setup, model-load, inference, parity and projected full-workload cost. Any such allocation is capped at one compute unit and 15 minutes, must stop on completion/failure, and must verify cleanup. No assumed GPU availability or setup-time estimate determines the result in advance.
