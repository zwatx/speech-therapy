# Fixed-model NISQA quality replication v1

This prospective replication tests the already saved 160-row recording-quality
models from the first study. It uses one new set of 40 metadata components and
does not refit, tune or modify any model. It is an engineering research task on
age-unverified read speech. It cannot establish child pronunciation, produced
phoneme, nonspeech, disorder or clinical validity. Learner judgments and model
promotion remain disabled.

## Frozen starting point

- Training plan SHA256: `797361b0a979a739f6d42d4d270c507d1a8e3a9de9172d613b7b6e3f2f71ebc5`.
- Saved prediction/model freeze SHA256: `06658f6617bdef7370864e98251eafbb4e61d72cbd7d244c6d8dee12c6f201b6`.
- Completed first confirmation SHA256: `257b654819760c280117ed455b38c684194cd12c8b27bf86c3715d74612ef821`.
- Original source, protocol, declarations and results remain unchanged. The first
  40 confirmation rows have been scored and are not an untouched test again.
- Actual Opus 5.5 reviewed the first result and recommended this fixed-model
  replication. That advice is not clearance to execute new code or read labels.
  The actual new declaration and source require an independent clear review.

## One metadata-only sample

Rebuild the original full 1,020-row TRAIN_LIVE component graph using the same
reader-group, source-reference and book edges. Exclude the complete pilot closure
and every component used anywhere in the first 200-recording study, including
unselected reserved rows. Store the complete graph and exclusion evidence.
Remaining reader groups, source references and books must be disjoint from those
excluded components. These are publisher provenance codes, not verified people.

Use salt `cadence-nisqa-quality-replication-40-v1` and the original digest syntax:
SHA256 of UTF-8 salt, NUL, namespace, NUL, value. Sort eligible phone components by
component hash then ID; choose the first 20. Sort eligible Skype components the
same way and choose the first 20 not already used. Select group and file within
each chosen component by the original group/file namespace hashes and lexical
tie-breaks. Store phone rows then Skype rows. Reserve each chosen component in
full. All selected rows have partition `replication`; all 40 components, groups
and paths must be distinct, with exactly 20 recordings per capture condition.

Selection may not use ratings, duration, amplitude, compressed size or waveform
properties. Size is used only for the subsequent fail-closed transfer-budget
check. This is the sole replication draw from the remaining components. Other
components remain a reserve. No second draw, replacement or subset rescue is
permitted after failure, invalid labels or an unfavorable result.

## Acquisition and phase barriers

The exact selected names, original directory entries and conservative body and
metadata budgets must be frozen before acquisition. Continue the same shared
256 MiB body and 16 MiB metadata ledger; preserve its counters, settings,
validator, old directory bindings, journal prefix and failed partial files.
A separate replication directory binding must not replace either old binding.
Use the previously verified complete directory snapshot without retrieving it
again. Only direct TRAIN_LIVE degraded WAV members are eligible. Keep the same
two-second GET pacing, zero retries, strict range/validator checks, first-429
terminal stop, exclusive output creation and exact size/CRC/SHA checks.

Audit every selected original with the unchanged waveform auditor. A failed
acquisition, audit, identity join or runtime check preserves the sample and
partial artifacts and prevents progression; there is no implicit restart.

Before new inference, repeat the first four original fitting recordings in their
frozen order and require bit-identical CPU feature/scalar hashes and frame/
preprocessing metadata against the first study. Load the same offline WavLM
checkpoint, extraction source, CPU runtime, processor and deterministic flags.
Use the original 16 kHz resampling, final-hidden mean/population-standard-
deviation pooling and six raw scalars. No GPU backend is used for this study.

Apply the saved 160-row PCA, scalers, fit-range bounds, ridge coefficients and
intercepts without fitting anything. Both saved lambdas remain 0.01. Use the
saved pooled mean and saved separate phone/Skype means, without recomputing them.
Keep unbounded predictions and retain every feature-clamped recording without
reweighting. Save all 40 feature vectors, original identities, encoder/runtime
provenance, four 40×5 prediction arrays and clamp diagnostics.

Freeze these artifacts and their model/input/source bindings. A separate clear
independent review naming the actual prediction-freeze SHA256 is required before
creating the label-reading phase or opening its numerical targets. Route combined
CSV rows by training identity before indexing target values; expose only these
40 selected TRAIN_LIVE rows. Keep the original strict nominal 1–5 numeric grammar
and exact empty/NaN missing whitelist. Do not trim, clip, map, drop or replace
labels. Distinguish invalid values, missing values, parse/coverage failures and
identity-join failures. Any incomplete set is inconclusive, never a pass.

## Fixed decision on the fresh 40 alone

Use the original five target dimensions in order: MOS, noisiness, discontinuity,
coloration and loudness. Report dimension and equal-weight macro MAE/RMSE, both
capture groups and paired differences against all three controls. Reuse the
unchanged original confirmation statistics: PCG64 seed 27092026, 10,000 common
40-row paired bootstrap draws and linear 2.5%/97.5% quantiles. The expected
little-endian int64 index hash is
`5eeaf74ea206f3bd6ceb0357fa0381fe1f984fbb1066d01cf6d6633fb91c79e2`.

Pass only if every original guard holds on these fresh recordings:

1. Candidate macro MAE is at least 0.05 lower than each control.
2. Every paired 95% interval upper endpoint is strictly below zero.
3. No dimension is more than 0.10 worse than the saved pooled mean control.
4. Both capture groups have nonpositive candidate-minus-capture-mean macro MAE.

The 0.05 margin applies to point estimates; intervals need only exclude zero.
Define outcome tiers before labels: **replicated** if all guards pass;
**directional, not replicated** if the candidate-versus-acoustic upper endpoint
is below zero but at least one guard fails; **not replicated** otherwise;
**inconclusive** for incomplete/invalid/parse/coverage/join-failed labels.
Never pool the first and new 40 for this pass decision. Any later pooled estimate
must be clearly descriptive and cannot change this outcome.

Report all failures and limitations honestly. Even a replicated pass would
support recording-quality prediction on this corpus only. It would not supply
the unfamiliar-child pronunciation or nonspeech truth needed for the broader
project goal. No author-test data may be presented as a fresh corpus.
