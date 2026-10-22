# Posterior pooling with fresh matched controls

This is a separate prospective route following the failed historical-parity preflight. Preserve the old protocol, source, declaration, partial outputs and failure exactly. The old route did not pass and will not be restarted. The fixed posterior pooling hypothesis remains unchanged; numerical differences from historical acoustic features are now descriptive, never a threshold for accepting or rejecting a recording.

Actual Opus 5.5 recommended this route in `work/core-model-next-method-20260927/opus-preflight-failure-review.json`. Its review supplies advice, not clearance for executing the new route. Actual execution requires a new declaration and independent source review. This protocol authorizes preparation of a small preflight and its separate-process verification only; full extraction and model fitting need later declarations and reviews.

## Fixed representation and input lineage

Use the same training-side child cohort: 1,040 recordings, 9,891 positions, 52 children aged 6–12 and 23 supported consonants. Author-test remains closed. Retain the original quantized ONNX full-vocabulary CTC probabilities and all 2,495+5 posterior bindings. Retain the original full-precision phonetic checkpoint, complete canonical prompt including vowels, canonical occurrence indices, mapping, windows, 13 scalar columns and row order. Quantized alignment probabilities and full-precision acoustic vectors are different numerical models; do not regenerate probabilities or change checkpoints.

The previously reviewed numerical core is unchanged: float64 canonical CTC forward/backward occupancies, log-normalized target weights q, fixed per-source-normalized two-frame context weights u, float64 acoustic accumulation persisted as float32. Impossible paths, invalid full-vocabulary normalization, malformed identities, nonfinite values and frame/width mismatches stop the run. Numerical tolerances remain the previously declared constants. This does not establish produced-phone, deletion or boundary truth.

Every candidate vector and its **fresh hard control** must share the same encoder forward. Hard controls use the unchanged original padded-window mean routine. Historical feature arrays remain hash-bound, and their 9,891-of-28,227 provenance and scalar equality are checked, but historical hard vectors are descriptive references only. Report per-row maximum absolute differences and counts of differing rows with no acceptance threshold.

## Fixed small CPU preflight

Use the same four declared probes: shortest fitting `000010168`, lower-median fitting `014190030`, longest fitting `001450051`, and global longest `000560117`. The fitting membership is the original seed17/speaker-fold0/word-group0, with whole-utterance word purging and no ratings consulted. The global-longest probe remains hardware-only and outside fitting. Retain all identities and explicit roles.

Use the passing Mac arm64 CPU route, exact Python/platform/package versions, Torch two threads and deterministic algorithms, original normalized processor, 24 frozen layers, float32 eager evaluation and one recording per forward. Bind the complete local source closure, numerical runtime/dependencies, protocol, advice, old failure, model, audio, posteriors and metadata. No changes to inputs or representation are chosen from diagnostics.

Run the four probes in the declared order, then repeat **all four** at the end: eight forwards. Require bit-exact candidate and fresh hard outputs for every within-run repeat. Historical differences do not gate these comparisons. Before retaining each artifact, check payload hashes and sizes, numerical invariants, geometry and identity. Recheck model, audio, posterior, references, sources and review at completion. Persist artifacts and hashes in an exclusive final report; persist the error message and completed counts on failure. Preserve partial outputs. No implicit restart, exclusions or substitute examples.

## Separate-process independent verification

Declare and source-review the verifier before inference. After a successful eight-forward run, launch it in a separate process using the same pinned runtime and original encoder/processor. Replay all four probes: four additional verification forwards, independently compute scalar-state CTC tables and an explicit dense context kernel, and reconstruct vectors and diagnostics. The encoder is shared, not independently implemented.

Fresh hard vectors must match the saved preflight controls bit for bit across processes. Independently summed candidate vectors use only the previously fixed absolute comparison tolerance `1e-6`; audit comparisons use the previously fixed `1e-10`. These verifier tolerances never relax the runner's bit-exact within-run candidate/hard repeat gate. The verifier checks report/declaration/review bindings, ordered coverage, every artifact and repeat, exact scalar/reference lineage, historical difference diagnostics and all no-label/no-fit flags. Any mismatch stops this CPU route. Failure artifacts remain intact.

Record total/per-clip time, process-lifetime peak memory in bytes on Darwin, occupancy/support/displacement and vector-distance diagnostics. They supply feasibility and integrity evidence, not accuracy. A full extraction requires successful preflight and verifier freezes plus independent results review.

## Predeclared downstream comparison

A later full extraction uses one process for all 1,040 recordings, pairing candidate and fresh hard vectors in every forward. Its own declaration fixes integrity checks and repeat probes. It may not silently resume or switch devices. Full extraction and training are outside this preflight's execution scope.

The later development comparison retains the original 75 cells: seeds17/29/43 × five speaker folds × five word groups, ordered fitting/selection/refit memberships and whole-utterance word purging. Train 75 candidate inner fits plus 75 candidate refits, and 75 fresh compact-control inner fits plus 75 compact-control refits. Both arms use fit-only PCA16, the same 13 scalar columns, head initialization, batching, ordinary five-vote NLL, stopping and equal compact/scalar mixture. All inner fits precede every refit, and every refit precedes outer scoring.

Use the same scalar component in both mixtures. Reuse historical scalar controls only after exact recipe, membership, checkpoint and prediction replays. If any scalar replay fails, the predeclared fallback is fresh scalar controls for **all 75 cells**, with their inner fits included before any refits. Never mix fresh and historical scalar components. Historical compact controls and mixtures remain descriptive only.

Compare the candidate mixture primarily with the fresh compact-control mixture. Preserve the original strict per-seed material NLL and rating0-discrimination screens and fold/age/all-23-phone safeguards; no averaging or selecting a successful seed, phone or age to rescue failure. Unsupported subgroups remain explicit. Later training declarations specify the complete numerical gates before fitting.

Even a successful development result uses an extensively explored cohort, not untouched confirmation. Independent child production/localization, recording-usability and nonspeech evidence remain necessary. No learner judgments, clinical eligibility or overall-goal completion follow from this experiment. Colab remains available under standing authorization, but a GPU route requires a separate declared and reviewed experiment with fresh matching controls and verified allocation, determinism, cost and cleanup.
