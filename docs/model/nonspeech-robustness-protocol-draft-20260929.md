# Fresh nonspeech admission check: draft protocol (revision 2)

**Status: DRAFT, not declared or run.** No audio has been acquired. It changes no model, threshold, filter or learner behavior.

- **Revision 1** wrongly said fold 5 was unused. Its disjointness scan missed the YAMNet studies.
- **Fable 5.1 review** ([review](../../work/robustness-sources-20260929/review-fable-v1.md), `claude-fable-5-1`) returned CHANGES-NEEDED.
- **This revision** applies that review. It revises the source pool from metadata only, with no audio opened. It needs a re-review before declaration.

## Questions

- **Part A (this protocol).** Among fresh, category-labeled natural nonspeech clips, how many does the fixed admission path admit under each of two fixed VAD policies?
- **Part B (blocked, separate).** Does that path keep natural isolated words from children with verified ages of 6–12?

The requirement in [campaign handoff](research-campaign-handoff.md) ("Non-speech rejection") stays **open** until Part B runs. The known cases (the dog `4-182395-A-0.wav`, the helicopter, and the crops) stay regression tests and are not part of this set.

## Part A source and freshness

- **Source.** [ESC-50](https://github.com/karolpiczak/ESC-50) at the pinned commit `33c8ce9eb2cf0b1c2f8bcf322eb349b6be34dbb6`.
  - Record the SHAs of `esc50.csv`, LICENSE and README.
  - ESC-10 clips are CC BY 3.0 and the other ESC-50 clips are CC BY-NC 3.0. Use is strictly noncommercial research.
  - Copy each clip's Freesound attribution into `selection.json`. Keep audio in ignored outputs and never redistribute it.
- **Earlier use: 60 ESC-50 files.**

  | Fold | Files | Study |
  | --- | ---: | --- |
  | 1 | 12 | `environment-v1` |
  | 4 | 24 | `environment-extension-v1` |
  | 5 | 24 (ESC-10) | `yamnet-speech-v1` / `yamnet-padding-v1` |

  The exclusion set is the union of `src_file` values of all 60 files. The declaration must re-derive it by scanning every folder under `research/audio-head/outputs/multiphone-20260927/` for ESC filenames, **excluding `esc50.csv`**. It maps each filename to its `src_file`, and fails unless the filenames found equal the union of the three earlier `selection.json` files (exactly 60).
- **Pool.** Folds 2, 3 and 5, minus the exclusion set. No audio from folds 2 or 3 has ever been fetched.
- **This revision's selection-revision reason (metadata only).** Revision 1's fold-5-only pool leaves 3 dog sources, fewer than 4, so its own stop rule fires. Pooling the three folds keeps dog, the known failure category.
- **Categories and subgroups (fixed before audio).**
  - **Vocalization:** `coughing`, `sneezing`, `breathing`, `snoring`, `laughing`, `crying_baby` (added in this revision, before any audio).
  - **Human activity:** `clapping`, `footsteps`, `brushing_teeth`, `drinking_sipping`.
  - **Animal:** `dog`, `cat`.
  - **Household:** `door_wood_knock`, `keyboard_typing`, `vacuum_cleaner`.
- **Metadata feasibility check** (unused sources in folds 2/3/5).

  | Category | Unused sources |
  | --- | ---: |
  | coughing, sneezing | 24 each |
  | footsteps | 23 |
  | keyboard_typing | 22 |
  | breathing, laughing, door_wood_knock | 21 each |
  | clapping, brushing_teeth | 20 each |
  | snoring, drinking_sipping, cat | 19 each |
  | dog | 18 |
  | vacuum_cleaner | 17 |
  | crying_baby | 11 |

- **Selection rule.** For each category, in the fixed order above:
  1. Rank eligible sources ascending by the lowercase hex SHA-256 of the UTF-8 bytes `nonspeech-v1|<src_file exactly as in the CSV>`. Break ties by `src_file` ascending.
  2. Take the first 4, skipping any source already chosen by an earlier category. In the current metadata, 4 ESC-50 `src_file` values span two categories, so this skip rule is needed.
  3. For each source, use the row with the lexicographically smallest `take`.

  This gives 60 clips. The salt `nonspeech-v1` never changes. If any category has fewer than 4 eligible sources, stop; never substitute. Write `selection.json` (rows, URLs, attributions, rule, exclusion set, revision reason) and hash it before any download.
- **Speech contamination.** No listening screen. Report results as "admissions by category label". Every clip stays in the denominator, and no clip is relabeled after the outcome.

## Fixed admission path

- **Raw reports.** Produced by `multiphone_research_audio`, following the same path as `multiphone_environment_challenge.py` (run section). The prompt is `multiphone_nonspeech.PROMPT`, written to `prompt.json` and pinned. The head is the pinned `unweighted-all-age` bundle and manifest.
- **Entry point.** `multiphone_short_vad_filter.filter_report`, pinned by SHA together with its approved-artifact pins (`COMPARISON_SHA`, `FOLLOWUP_SHA`, `BASELINE_SOURCE_SHA`). One Silero pass gives both policies:
  - `default250`: `min_speech_duration_ms=250`
  - `short100`: 100 ms

  The other Silero parameters are fixed: threshold .5, neg_threshold .35, min_silence 100 ms, pad 30 ms, Silero commit `5cd79456…`. Record the full SHA in the declaration.
- **Recorded per clip.**
  - Phone-evidence decision (`multiphone_evidence_gate.assess`) and its recognized-token count.
  - VAD-250 and VAD-100 decisions.
  - **Co-primary outcomes, with no preference between them:** combined-250 (`default250/finalreport.json` → `decision.ratingAvailable`) and combined-100 (top-level `finalreport.json` → `decision.ratingAvailable`). "Admitted" means `ratingAvailable` is true.
- **Head independence.** The decision reads only the 16-kHz waveform, the CTC posteriors and the Silero probabilities (`multiphone_evidence_gate.py` `assess`; `multiphone_vad_study.py`; `multiphone_short_vad_filter.py`). For the same WAV, CTC output was byte-identical across prompts ([position-filter report](multiphone-position-filter-report.md)).
  - The head and prompt affect only whether the run completes and which targets are masked. A complete raw report requires the head to load and the prompt to validate.
  - Runtime uses the earlier `unweighted-all-age` head and the prompt `B AO1 L`.
  - **No filter is integrated with the ages 6–12 bundle.** Results carry over to it only under the same pinned CTC contract, CTC worker, Silero artifacts, parameters, thread count and 16-kHz waveform.
- **Conversion.** ffmpeg to mono 16-kHz PCM16, no trimming or normalization. Pin the ffmpeg binary SHA and version, the exact command, the conversion helper SHA, and the original and converted SHAs.
- **Pins.**
  - The ESC commit and files.
  - The raw adapter, contract, CTC checkpoint, worker, node, phonetic snapshot, `unweighted-all-age` manifest SHA and prompt JSON SHA.
  - Silero `silero_vad.jit`, `utils_vad.py` and `PARAMS`.
  - Gate and filter sources.
  - Python, torch, `requirements.lock`, platform, and threads=2 on local CPU.
- **Failures.**
  - **Pre-run environment check:** before any download, run `approved_context()` once. If it fails, stop and revise the protocol; this is not a per-clip failure. The approved plans record `macOS-27.0-arm64-arm-64bit-Mach-O`.
  - Each clip is attempted once.
  - A download or hash mismatch stops the run; never substitute.
  - Any other failure stays in the denominator as "failed". It is never counted as a rejection and never rerun unless the retry is declared and disclosed.
  - Stale `.partial` outputs are reported.
  - An offline verification step recomputes every reported count from the bound per-clip reports.

## Claims Part A does not support

With 4 clips per category, per-category rates carry no meaning. With 0/60 admitted, the exact two-sided 95% upper bound is about 6%, and it applies only to this designed category mix. The report must not claim any of the following:

- a general false-acceptance rate, or that speech rejection is validated;
- anything about lost speech or retention;
- that the handoff requirement is met;
- a difference or preference between 250 ms and 100 ms;
- that admitted clips contain no speech;
- that the clips were unseen by upstream models (whether Silero/CTC pretraining included these Freesound recordings is unknown);
- relevance to children or to speech disorders;
- any threshold or policy change.

## Part B: child speech retention (blocked)

This part needs natural isolated words from children with verified ages of 6–12.

- **Kennedy et al. (Zenodo 200495): not eligible.** It has 11 children with a mean age of 4.9, so at least one child is under 6. No archive member can be tied to an age: the 800-member central directory has no non-WAV files and names only child number, sex and native status ([listing](../../work/robustness-sources-20260929/kennedy-archive-listing.json)). The associated publication was not checked for per-child ages. Even if it listed them, the 6–12 subset would be tiny and unverifiable per file.
- **Best candidate: PERCEPT-R** ([plan](percept-r-research-plan.md)). It needs a user-signed PhonBank distribution form. Part B gets its own protocol and fixed selection after access, before any audio or ratings are opened.

## Before declaration

1. Revision 2 was re-reviewed by Fable 5.1 ([review](../../work/robustness-sources-20260929/review-fable-v2.md)): all ten findings addressed, four text gaps remaining. Those four are applied here (the scan excludes `esc50.csv`, the raw-report producer is named, the cross-category rule is defined, and the environment check runs before any download). According to the reviewer, no further full review is needed.
2. Implement the selection, acquisition and run worker, with synthetic tests. The declaration must re-derive the exclusion set and counts and fail on any shortfall.
