# Posterior pooling: bounded CPU preflight

This prospective protocol fixes one label-free extraction hypothesis before new posterior arrays or encoder outputs are inspected. It is a numerical and feasibility preflight, not a model accuracy experiment. No fitting, selection, outer scoring or learner judgments are authorized by this protocol. Actual execution also requires a source-bound declaration and a separate independent review of that declaration.

The overall pronunciation research goal remains active. The retained model and existing scientific artifacts remain unchanged.

## Hypothesis and scope

The current phonetic representation averages final hidden states inside one canonical Viterbi interval, padded by two frames. The candidate instead averages over alternative plausible canonical locations. Previous middle-layer, temporal-bin, sequence-scalar and rare-error loss studies did not test this exact pooling rule. Their negative or mixed results remain relevant; there is no evidence yet that this rule improves the model.

Canonical locations are hypotheses conditional on the complete prompt. They are not observed phone boundaries or produced-phone labels. A canonical graph can force an omitted target onto a neighboring sound. This method does not solve deletion, insertion, localization truth or nonspeech detection.

Only the existing training-side child cohort aged 6–12 is eligible: 1,040 recordings, 9,891 positions and 23 supported consonants. Author-test remains closed. A preflight uses a fixed small subset and the cohort's longest recording; the full extraction and subsequent 75-job development study require later declarations and reviews.

## Unchanged inputs and control lineage

Use the existing quantized ONNX phonetic-model CTC log probabilities, with their original full vocabulary, canonical mapping and frame geometry. The complete position-scalars report binds all 2,500 training-side posterior files, including five added CTC jobs. Join the exact child clip identities to those bindings; do not assume that the original 2,495-file cache alone covers the cohort.

Acoustic hidden vectors come from the original full-precision `facebook/wav2vec2-lv-60-espeak-cv-ft` checkpoint, revision `ae45363bf3413b374fecd9dc8bc1df0e24c3b7f4`. Its numerical outputs are distinct from the quantized alignment model. Do not substitute WavLM or regenerate CTC probabilities with the full-precision checkpoint. The hidden-frame count must exactly match the selected CTC frame count.

The historical reference is the 9,891-row child subset of the 28,227-position position-phonetic extraction, used by lexical-seed-replication and the passing temporal-extraction parity path. Bind that exact reference, row ordering and 13 unchanged scalar columns. Do not substitute the older 14,837-row feature export. Each row retains its original identity, `canonicalIndex`, interval and estimated pooling window.

Recompute historical hard means in the same encoder forward using the unchanged historical pooling routine and its float64 mean accumulation followed by float32 persistence. Require exact array equality with the bound historical vectors. Do not use a weighted delta posterior to compute the parity control, widen a tolerance or silently reuse controls after a mismatch.

## One fixed numerical rule

The canonical token sequence includes vowels and all mapped prompt tokens. A row's zero-based `canonicalIndex` j refers to this full sequence, not to an ordinal among consonant targets. Its CTC token state is s = 2j + 1. Adjacent equal tokens retain the original skip restriction and require a separating blank.

Using the existing forward/backward table convention, frame t's log occupancy is:

`log_gamma[t,s] = A[t+1,s] + B[t+1,s] - logZ`.

A includes emissions through t; B includes subsequent emissions. Compute tables and normalization in float64 log space. Require finite `logZ`, agreement of forward and backward sequence likelihoods, per-frame state occupancy sums equal to one within the declared numerical checks, and total occupancy of each canonical token state at least one within rounding. Structurally unreachable table cells may be negative infinity. Impossible paths, NaNs, invalid dimensions, bad token IDs, malformed log probabilities or zero normalized mass stop the preflight without dropping or replacing examples.

Normalize each target state's occupancy over time to q using log-sum-exp. Fix a two-frame context radius and normalize the box for each source frame k by its number of valid neighboring frames c(k):

`u[t] = sum_k q[k] * 1(abs(t-k) <= 2) / c(k)`.

This is the posterior expectation of the historical one-frame padded-window mean and preserves source-frame mass at clip edges. It requires no additional global renormalization. Pool `sum_t u[t] * hidden[t]` in float64 and persist float32. This changes temporal support and weighting; it does not reproduce the historical uniform mean for every multi-frame Viterbi interval.

There is no posterior temperature, alternative kernel, entropy feature, deletion branch, learned attention, mapping change or search over recipes. Label-free diagnostics cannot be used to choose another rule or a subset after seeing outputs.

## Synthetic verification before declaration

Use direct enumeration of all valid paths on tiny independent CTC graphs as the oracle. Cover repeated tokens, adjacent repeats, edge states, long blank runs, concentrated paths, the minimum frame count needed by repeats, impossible paths and extreme negative log values. Compare sequence likelihood, all-state occupancies, q, u and pooled vectors with direct sums. Check the empty all-blank sequence explicitly if supported by the numerical API; it cannot produce a target vector.

Check exact historical pooling with the original routine separately from the weighted implementation. Verify dtype, shape, finiteness, normalization, numerical model separation, identity joins, canonical indices, window geometry, source/runtime drift, failure preservation and repeat checks. Synthetic passes do not establish integrity of actual corpus inputs or encoder behavior.

## Fixed small real-data preflight

Before reading actual posterior payloads or running the encoder, declare clip identities by an outcome-independent duration rule. Select the shortest, median and longest distinct clips inside the current seed-17/speaker-fold-0/word-group-0 fitting membership, after the original whole-utterance word purge. Determine membership from the original ordered job and rating-free clip/position identities. Duration ties use clip-ID order; use the lower median of the sorted distinct eligible clips. No target ratings determine selection.

Also include the global longest recording among all 1,040 clips as a label-free memory/runtime probe, deduplicating it if already selected. Mark its role explicitly; do not present it as fitting-side if it is outside that membership. No labels, fits or predictions are permitted on it.

Bind all selected audio, posterior metadata and payload hashes, model files, vocabulary/mapping, historical vectors, scalar/reference ordering, imported source closure, dependency source and runtime evidence in the declaration. The runner uses only its rating-free manifest, exact references and bound input files. It must not traverse broad score files merely to obtain clip identity.

Use the passing temporal extraction's Mac arm64 CPU route with Torch 2.8.0, Transformers 4.57.6, NumPy 2.2.6, two Torch threads, float32 eager evaluation, unchanged processor normalization, one recording per forward and deterministic execution. Record the actual Python/platform and processing evidence. A different device, platform class or numerical runtime is a new route.

Run all selected clips, checking input hashes, full-vocabulary log-softmax normalization, CTC/hidden geometry, posterior invariants and exact historical hard-mean parity before retaining candidate outputs. Repeat the selected shortest and global longest clips at the start and end, requiring bit-exact candidate and hard-control outputs. Save per-clip artifacts and an exclusive final freeze; preserve partial outputs and a failure record on error. No implicit restart, replacement, exclusion or recipe change is permitted.

Record total and per-clip time, peak memory with the measurement method and units, occupancy/support/displacement diagnostics, and candidate-versus-control vector distances without ratings. No accuracy claim follows from these measurements. Finite valid extraction, exact control parity and repeatability support a later complete extraction; the diagnostics do not establish that the representation helps.

## Accelerator and downstream boundaries

The earlier temporal extraction processed all 1,040 clips in about 215 seconds on this Mac. That is evidence about the old route, not the new posterior implementation's runtime. Measure this preflight first.

Colab remains available under the user's standing compute authorization. If measured CPU feasibility motivates GPU use, declare and independently review a separate route. Candidate and fresh hard controls must share the same GPU forwards; new compact controls must be trained on those hard-control vectors under identical partitions and recipes. Historical CPU controls become descriptive references. Do not silently relax CPU parity, invent a tolerance or certify GPU determinism from the previous benchmark. Actual GPU allocation, reproducibility, cost accounting and cleanup require their own verified execution plan.

A later development study, if justified, preserves the existing 75 jobs: seeds 17/29/43 crossed with five speaker folds and five word groups; original whole-utterance word purging and ordered selection/refit memberships; fitting-only PCA16 plus the 13 unchanged scalars; original compact/scalar mixture, head initialization, batches, ordinary five-vote NLL and stopping. All inner fits precede all fresh refits, and all refits precede outer scoring. Preserve the strict per-seed material and subgroup safeguards without averaging or selecting a successful seed. This preflight does not authorize those stages.

The reused development cohort cannot supply untouched confirmation after the extensive prior experiments. Even a successful later study requires independent child production/localization, recording-usability and nonspeech evidence before real-use claims. No clinical eligibility, learner judgments or overall-goal completion can follow from this preflight.
