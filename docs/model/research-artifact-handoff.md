# Research model artifact handoff

Use the [current decision](current-multiphone-decision.md) for model conclusions.
This guide identifies the existing runnable artifacts and their input contracts.
Outputs describe subjective corpus ratings; learner pronunciation judgments
remain disabled. The newer expanded-fitting experiments do not replace the
four original portable bundles.

## Choose an entry point

| Starting input | Entry point | Required material | Result |
| --- | --- | --- | --- |
| Already extracted model features | `multiphone_research_inference.load_head(...).predict(...)` | One complete seven-file bundle, the inference loader, pinned `multiphone_models.py`, NumPy and PyTorch | Three rating probabilities per requested position |
| A permitted WAV and an explicit canonical prompt | `python -m position_inference.audio` | This repository and its pinned Python/Node dependencies, q8 CTC cache, full-precision phonetic snapshot, one original bundle and schema-2 prompt | Position identities, extracted features, recording measurements and raw rating probabilities |
| A completed raw inference report | `python multiphone_short_vad_filter.py` | Pinned Silero model/helper and the research workflow's historical manifests and source dependencies | `finalreport.json`; rejected targets have null probabilities |
| Saved experimental predictions | The relevant study's `verify` command | Its declared plan, exact phase freezes, checkpoints, cached features, source and input artifacts | Reconstruction of that experiment's saved report |

The feature-only loader does not open the original training archive. Raw-WAV
extraction and filtering remain repository-bound workflows; copying a head's
seven files does not copy their encoders, caches or provenance dependencies.
Use the existing environment in `research/audio-head/.venv`: Python 3.13,
NumPy 2.2.6 and PyTorch 2.8.0. The full research dependency versions are in
[`requirements.lock.txt`](../../research/audio-head/requirements.lock.txt).

## Original portable bundles

The four directories under
[`phonetic-final`](../../research/audio-head/outputs/multiphone-20260926/phonetic-final/)
are `unweighted-all-age`, `unweighted-child-only`, `weighted-all-age` and
`weighted-child-only`. Use the exact caller-pinned manifest hashes in the
[research README's bundle table](../../research/audio-head/README.md#use-a-completed-research-head).
The original `weighted` names mean **rating-class weighting**. They do not mean
the later recording/sound-unit weighting used by the expanded experiments.

The feature API accepts raw `float32[N,1037]` values: 1,024 pinned phonetic
target-window features followed by the 13 ordered CTC scalars. Supply integer
canonical target IDs in the same row order. The supported phones are
`B P M T D N K G F V S Z SH CH JH L R W Y HH TH DH NG`; `ZH` is unsupported.
Array shape alone cannot verify the extractor, prompt or position identity.

These full-data fits have no independent performance score. Their architecture
performed worse than scalar features under the later complete-utterance word
exclusions. Retain that limitation when using them; newer mixture scores do not
describe these bundles.

## Run a raw-audio example

Run commands from `research/audio-head`. The
[occurrence-aware audio guide](multiphone-position-audio-report.md#reproduce-a-verified-repeated-position-case)
contains a complete command with verified WAV, prompt, bundle and contract hashes,
and an offline verifier for the saved seven-case check. Use a fresh output
directory; do not overwrite completed or partial runs.

For another permitted recording, provide its actual hash and an explicit
schema-2 prompt containing canonical words/phones and target word/phone indices.
Input is mono 16 kHz PCM16 WAV lasting 0.1–30 seconds. Repeated sounds are allowed
at distinct positions. The adapter does not resample audio, infer the intended
prompt or establish what was actually spoken.

The [filter guide](multiphone-position-filter-report.md#use-the-existing-filter-after-occurrence-aware-inference)
provides a complete follow-on command. Consume only its `finalreport.json` and
check `decision.ratingAvailable`; raw and intermediate reports can still contain
scores that the final filter withheld. The known dog recording passes this
exploratory filter, so acceptance does not establish speech or prompt correctness.

## Newer experimental candidates

The expanded, unit-weighted and seed-replication study directories retain
scalar/PCA checkpoints for specific speaker/word cells and fixed equal mixtures.
They are evaluation artifacts. Their replay helpers require the original study
cohort, cached features and fitting metadata; they are not compatible with the
portable `load_head` interface or an arbitrary-WAV caller.

The [seed protocol](multiphone-lexical-seed-replication-protocol.md) fixes both
objectives at seeds 17, 29 and 43. See the current decision for completion status
and verified results. Do not choose a seed or cell by its evaluation outcome.
A new portable mixture would need an explicit fitting or checkpoint-selection
rule, a defined arbitrary-input interface and its own parity verification.

## Verification scope

The [bounded handoff inspection](../../work/lexical-seed-replication-audit-20260927/handoff-inspection.json)
rechecked four manifests, their 24 bound files, 26 raw-interface source/dependency
pins and four example-input pins without finding a mismatch. It did not rerun
inference, tests, encoder-cache verification or the full filter dependency closure.
Actual portable and raw-audio replay evidence is linked in the README and audio
guide. The [model card](multiphone-research-model-card.md) and
[accessible-data assessment](accessible-data-next-step.md) retain the validation
and data-access limits.
