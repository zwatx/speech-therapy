# Occurrence-aware research WAV verification

Add a separate schema-2 adapter for explicit canonical word/phone positions.
Keep the schema-1 adapter, its duplicate-phone rejection and all four existing
research bundles unchanged. The new adapter accepts repeated supported
consonants at distinct positions, preserves caller target order and IDs, and
rejects duplicate IDs, duplicate positions, unsupported targets, malformed
prompts and impossible CTC paths. It retains the existing audio constraints,
offline encoders, 1,037 feature columns and research-only probability meaning.

The extension contract binds the exact parent contract and both old and new
runtime sources. All word and phone indices are zero-based integers, excluding
booleans. The supplied transcript must exactly join supplied words. At most
200 words, 512 canonical phones and 512 target occurrences are allowed.
Repeated model target IDs are valid; the word/phone position identifies the
occurrence. Equal adjacent canonical CTC tokens require an intervening blank.
Pooling windows may overlap because the fixed context extends two frames.

## Fixed implementation checks

Use the completed, hash-pinned author-training position export as the parity
reference. Choose child clips (ages 6–12) from metadata only: the first clip by
ID with a repeated supported consonant within one word, the first with repeats
across words, the first with adjacent equal consonants, the first containing
only added positions, and the first containing only original positions. Keep
distinct clips in that criterion order. Then repeatedly add the child clip
covering the most remaining supported phones, breaking ties by clip ID, until
all 23 phones are covered. Do not consult ratings, model probabilities or
performance when choosing cases.

This selects seven recordings and 66 positions: 000010115, 000010035,
000010113, 000530027, 000010011, 000260096 and 014390134. Request every supported
occurrence in each clip; reverse target order for odd-numbered cases (zero-based).
Assign the four existing variants cyclically in this order: unweighted all-age,
unweighted child-only, weighted all-age, weighted child-only. Freeze the cases,
prompts, audio, reference matrices, geometry/posteriors, bundle manifests/files,
contract, protocol, sources and runtime paths before raw inference.

Run the actual offline q8 CTC and full-precision phonetic encoder on each WAV,
then the assigned existing bundle. Require exact CTC bytes, all 1,037 feature
values, canonical indices, target IDs/order, occupancy/pooling windows, scalar
diagnostics and head probability replay against the expanded export. Retain
recording measurements and subjective rating-probability limitations. Recheck
input/source hashes before publishing results. Use fresh output paths and
retain failures; no implicit retry, overwrite or resume.

Focused synthetic tests cover repeats, caller ordering, adjacent-token blanks,
more than 23 requested occurrences, bounds, duplicate identities, malformed
prompts, unsupported targets, contract/source changes and publication failure
when an input changes. Run the existing schema-1 tests unchanged. A separate
offline verifier reconstructs the saved parity checks without encoder inference;
an independent reviewer checks implementation and actual artifacts.

This verifies software fidelity and occurrence identity. It does not measure
pronunciation accuracy, supply verified phone timing, establish nonspeech
rejection, retrain or promote expanded heads, or enable learner judgments.
Generic caller audio retains unspecified author-partition provenance. The
verification cases themselves come only from the pinned author-training data;
author-test remains closed and no Colab compute is required.
