# Fresh nonspeech admission check: Part A result (2026-09-29)

**Status: Part A executed and verified. The broader nonspeech-rejection requirement remains open.**

The unchanged admission path completed all 60 declared ESC-50 clips from 60 distinct fresh sources, with no pipeline failures or stale `.partial` outputs. It admitted **3/60** under the fixed 250 ms policy and **8/60** under the fixed 100 ms policy. These are co-primary admissions by category label in the designed mix. No policy preference or threshold change follows from this check.

Part B has not run. Natural isolated-word retention for children with verified ages 6–12 still requires access to PERCEPT-R after the user signs the PhonBank distribution form. No filter was integrated into the ages 6–12 bundle, and the retained model and learner behavior are unchanged.

## Co-primary observations

| Fixed policy | Admitted | Rejected by this path | Failed | Denominator |
| --- | ---: | ---: | ---: | ---: |
| Combined 250 ms | 3 | 57 | 0 | 60 |
| Combined 100 ms | 8 | 52 | 0 | 60 |

The phone-evidence decision admitted 36/60. The separate VAD decisions admitted 3/60 at 250 ms and 8/60 at 100 ms. All VAD-admitted clips also passed phone evidence in this set. A single Silero probability trace per clip produced both VAD policies.

Each category has four clips. The following counts describe this selection; four observations do not establish a meaningful per-category rate.

| Category label | Clips | Combined 250 ms admissions | Combined 100 ms admissions |
| --- | ---: | ---: | ---: |
| `coughing` | 4 | 1 | 2 |
| `sneezing` | 4 | 0 | 1 |
| `breathing` | 4 | 0 | 0 |
| `snoring` | 4 | 1 | 1 |
| `laughing` | 4 | 1 | 1 |
| `crying_baby` | 4 | 0 | 1 |
| `clapping` | 4 | 0 | 0 |
| `footsteps` | 4 | 0 | 0 |
| `brushing_teeth` | 4 | 0 | 0 |
| `drinking_sipping` | 4 | 0 | 0 |
| `dog` | 4 | 0 | 1 |
| `cat` | 4 | 0 | 0 |
| `door_wood_knock` | 4 | 0 | 1 |
| `keyboard_typing` | 4 | 0 | 0 |
| `vacuum_cleaner` | 4 | 0 | 0 |

| Fixed subgroup | Clips | Combined 250 ms admissions | Combined 100 ms admissions |
| --- | ---: | ---: | ---: |
| animal | 8 | 0 | 1 |
| household | 12 | 0 | 1 |
| human activity | 16 | 0 | 0 |
| vocalization | 24 | 3 | 6 |

## Admitted clip identifiers

These are the dataset labels. No listening screen, speech-contamination relabeling, outcome exclusion, substitution, or retry occurred. Audio stays in ignored research outputs and is not redistributed.

| Filename | Category label | Combined 250 ms | Combined 100 ms |
| --- | --- | --- | --- |
| `3-145487-A-24.wav` | `coughing` | Admitted | Admitted |
| `2-85292-A-24.wav` | `coughing` | Rejected | Admitted |
| `5-187979-A-21.wav` | `sneezing` | Rejected | Admitted |
| `5-235874-A-28.wav` | `snoring` | Admitted | Admitted |
| `3-152997-A-26.wav` | `laughing` | Admitted | Admitted |
| `3-151080-A-20.wav` | `crying_baby` | Rejected | Admitted |
| `3-155312-A-0.wav` | `dog` | Rejected | Admitted |
| `5-235644-A-30.wav` | `door_wood_knock` | Rejected | Admitted |

## Declaration, execution, and verification

- Implemented the metadata selection, immutable declaration, acquisition, once-only run, and offline verifier in [the worker](../../research/audio-head/nonspeech_robustness/README.md). No dependencies were added.
- Fable 5.1 [implementation review](../../work/nonspeech-robustness-20260929/review-fable-v1.md) returned READY-TO-DECLARE with no blockers; reported `claude-fable-5-1` usage was verified. Its suggested direct raw-source/head/CTC lineage checks were added and tested before declaration.
- All 59 relevant tests passed: 30 new worker tests and 29 existing raw-adapter, phone-evidence, and 250/100 filter regression tests. They include cross-category sources, master-index exclusion, chunk boundaries, shortfalls, provenance tampering, global integrity stops, failed-clip denominators, and no implicit second attempt.
- A pre-audio declaration audit was interrupted to speed scanning of multi-gigabyte numeric historical reports. No output declaration, selection, audio download, or clip attempt existed then. A literal `.wav` byte prefilter preserves the same matching rule and chunk overlap; all 59 tests passed again before the successful declaration.
- The global approved-environment check passed before every acquisition stage. Python’s default HTTPS trust failed during metadata preflight; the pinned system curl succeeded with TLS verification, user configuration disabled, HTTPS-only redirects, size limits, and zero retries. This change preceded declaration and all audio downloads.
- The recursive history audit excluded `esc50.csv` and found exactly the 60 filenames in the three earlier pinned selections. Every selected source is disjoint from their source union. The fixed folds 2/3/5, SHA-256 salt `nonspeech-v1`, category order, four-source rule, and lexicographic take rule were preserved.
- Public commit-to-tree-to-blob metadata bound each original before acquisition. Original Git blob identities, original and converted SHA-256 values, source attributions, dataset licenses, and exact conversion commands are recorded. Conversion was mono 16-kHz PCM16 with no trimming or normalization.
- Selection and declaration were frozen before audio at 2026-09-29T18:55:59.461242+00:00. All 60 acquisition records were ready. Every clip was attempted once on the local Mac CPU with two threads. Colab was unused; no new model fitting, policy/threshold adjustment, or learner deployment occurred.
- The [offline provenance verifier](../../work/nonspeech-robustness-20260929/verification.json) passed. It re-read and hashed the declared sources, runtime, head, CTC/Silero artifacts, audio, raw reports and derived artifacts, and reconstructed every reported count without model or filter execution.
- The [separate independent count audit](../../work/nonspeech-robustness-20260929/independent-result-audit.json) passed, checking all 180 bound raw/combined reports and every overall, category, and subgroup count. It also checked shared probability traces, recorded decisions, one-attempt coverage, failed-clip accounting, and the empty partial-output inventory.
- The main app builds were not run: this change adds an isolated research worker and report, with no app implementation changes. The pinned Node worker emitted its existing module-type warning; all 60 forwards completed.

| Artifact | SHA-256 |
| --- | --- |
| [Declaration](../../research/audio-head/outputs/nonspeech-robustness-20260929/v1/declaration.json) | `dd84a75990a5c1ff76298399df91b0a8aed0dd302ee03b4aeb454a7d4d44ab95` |
| [Selection](../../research/audio-head/outputs/nonspeech-robustness-20260929/v1/selection.json) | `84734b25f284d14b821f6dd84b52a8bf4e72ad5a2a999b733c54e160b9dec6c9` |
| [Acquisition](../../research/audio-head/outputs/nonspeech-robustness-20260929/v1/acquisition/manifest.json) | `b741e40cf3ddc9e57e52cf7e65e8bea210d8933432b385c90a6b2db144ee26b4` |
| [Result](../../research/audio-head/outputs/nonspeech-robustness-20260929/v1/results/report.json) | `8c9be8217088ef7318fb0258763f5f8e0fe628248fc3cb77ea3a19f50e549c85` |

Per-clip Freesound attribution and ESC-10 CC BY 3.0 / other ESC-50 CC BY-NC 3.0 dataset licensing are recorded in selection. Use is strictly noncommercial research.

## Interpretation and next step

This closes the exact, predeclared Part A run. Category-labeled nonspeech clips were admitted under both fixed policies. That observation does not validate speech detection, prompt matching, pronunciation correctness, or speech retention.

The counts do not estimate a general false-acceptance rate, establish a difference or preference between policies, prove absence of speech in admitted clips, or establish that recordings were unseen in upstream Silero/CTC pretraining. They provide no evidence specific to children or speech disorders. No model, policy, threshold, or learner behavior was changed.

The campaign’s nonspeech-rejection requirement remains **open**. Part B needs its own fixed protocol and selection after lawful PERCEPT-R access, before audio or ratings are opened; see the [PERCEPT-R plan](percept-r-research-plan.md). The user-signed PhonBank distribution form remains the blocking action. These 60 clips are now consumed research evidence and cannot be reused as a fresh evaluation set.

## Result review and handoff

Fable 5.1 returned **CLEAR**, with no blockers in the [result review](../../work/nonspeech-robustness-20260929/review-result-fable-v1.md); reported `claude-fable-5-1` usage was verified. It checked counts, coverage, co-primary reporting, limits, and recorded hash consistency. Actual byte hashes were recomputed by the offline verifiers, not by the read-only reviewer.

The [frozen protocol source](nonspeech-robustness-protocol-draft-20260929.md) retains its pre-declaration status text; this report and the bound declaration record execution. The [consumed-source ledger](../../work/nonspeech-robustness-20260929/consumed-esc-sources.json) records 120 distinct sources across the previous studies and this run. A future fresh panel must account for the new 60 sources as well as the historical 60; this closed worker must not be redeclared to claim fresh evidence.

[Execution observations](../../work/nonspeech-robustness-20260929/execution-observations.json) record that the run and offline verification were observed complete by 14:08:34 Chicago time, before the requested 14:20 safe pause. This is a completion-by observation, not a precise batch end timestamp.
