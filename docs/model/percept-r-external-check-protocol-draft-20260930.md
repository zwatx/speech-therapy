# PERCEPT-R: fresh external check of the retained model, and child-speech retention (draft protocol)

**Pre-run status (2026-10-01): reviewed and ready for declaration.** Originally written on 2026-09-30. Fable 5.1 reviews v2/v3 and the saved-artifact audit delta are clear; the fixed scientific choices below are unchanged. Results are recorded separately.

When this draft was written:
- **Opened:** the corpus member list, the Phon/CHAT field names, participant ages, the `segment` times, the `ARPABET Target`, `study` and `phase` tiers, and whether the rating tiers are present.
- **Not opened:** rating values (`responseAve`, `responseCorrect`, `responseTotal`), audio content, model features and model predictions.

The corpus is registration-access PhonBank data ([source note](percept-r-research-plan.md)). It is noncommercial research use only, must be cited, and is never redistributed. Any use must cite at least one PERCEPT-R reference from the corpus page.

## Why this matters

Every model result so far rests on 52 extensively reused children. PERCEPT-R provides children aged 6–12 whom the retained model has **never seen**, rated by listeners on their /r/ productions. It gives the project two things for the first time:

1. A **fresh external check** of the unchanged retained model on unfamiliar speakers and words (/r/ only).
2. The missing **speech-retention half** of the nonspeech study: natural isolated child words, ages verified by corpus metadata.

## What the data are (structure only)

- **Version.** 286 speaker folders and 2,019 sessions. The archive's SHA-256 is `58953584…62` ([manifest](../../research/audio-head/outputs/percept-r-source/source-manifest-v1.json)).
- **In-range speakers.** Ages come from Phon XML (`<age>`); the CHAT `@ID` age fields are empty. There are **204 folders / 1,629 sessions** where every session is at ages 6–12. The download pilot fetched `CRESULTSMOSAIC_111/PRE-1.wav`; speaker 111 is in the sealed TEST group, so that file is stored but never decoded under this protocol.
  - Five IDs appear in two study folders (for example BFS_25 and CPF_25). The corpus paper says overlapping speakers share their ID number, so the unit is the **numeric speaker ID**: **199 speakers**.
- **Token unit.** One record is one word-level utterance, with:
  - `segment start/end` (seconds) in the session WAV;
  - an `ARPABET Target` canonical pronunciation;
  - `study`, `phase` (PRE/TX/DP/POST/FU/MID/REG) and `session`;
  - ratings: `responseCorrect` (the number of "fully rhotic" listener responses) and `responseTotal` (the number of listeners).
- **Rating method.** Per the corpus paper, the ratings are binary listener judgments. Crowdsourced listeners rated most tokens and trained listeners (SLPs or students) rated the rest, depending on the study. No per-token rater-type field exists.
- **Eligible tokens.** Records whose ARPABET target contains **exactly one consonantal `R` and no `ER*`**, so the single rated rhotic is the consonant our model scores. There are 67,531 such tokens in range (36,128 prevocalic, 31,066 postvocalic, 337 intervocalic). 16,923 records with r-colored vowels and 687 without ARPABET are excluded by this rule, fixed before any outcome.
- **Audio.** Session WAVs are mono, 44.1 kHz, 16-bit (from the pilot). Each folder also has a Praat TextGrid.

## Fixed speaker split (sealed test)

The split was written before any audio or rating was processed: `work/percept-r-media-20260930/speaker-split-v1.json`, SHA-256 `88ae2087399514fd810d118a27dfed9a6fe7b8764a713448163f7f8b83f80f70`.

The 199 speaker IDs are ranked by SHA-256 of `percept-r-split-v1|<id>`. The first 119 (60%) form **DEV** and the other 80 form **TEST**. By session count, that is 1,004 DEV and 625 TEST sessions.

- **Speaker-disjoint.** All sessions, phases and studies of a speaker stay on one side.
- **TEST is sealed.** No TEST audio is decoded, featurized, scored or listened to, and no TEST rating is read, until a separately declared future comparison. Examples would be a PERCEPT-R-trained /r/ head versus the retained model, or a fresh validation of an advanced candidate.
- **Everything in this protocol uses DEV only.**
- The split is not stratified. The token counts per study are uneven (for example, `staRt` falls wholly in TEST), so per-study results are descriptive.

## Part 1: frozen retained-model external check (DEV)

**Model.** The retained ages 6–12 bundle, unchanged (manifest `bc62f1e4…bf`), fed by the existing occurrence-aware extractor `position_inference.audio`. The prompt is schema-2: one word from the orthography, its phones from `ARPABET Target`, and one target at the `R` position. The age guard uses the session's Phon XML age. There is no fitting, calibration or threshold choice.

**Token sample (fixed before audio).** DEV has 44,248 eligible tokens, but speakers range from 13 to 2,585 tokens each (median 120). Each extraction takes about 5 s (the median of 94 earlier runs; mostly CTC worker start-up).

For each DEV speaker, take **up to 40** eligible tokens with the lowest SHA-256 of `percept-r-external-v1|<folder>|<session>|<record id>`. That gives **4,539 tokens**, with every speaker represented and no speaker dominating. This cap was fixed for compute cost and speaker balance before any audio or rating was read.

Two further rules, also fixed before audio:
- Tokens containing a symbol outside the extractor's mapping (6 DEV tokens, all `AX0`) are counted and excluded.
- Segments shorter than 0.1 s (1 DEV token) are counted as reader failures.

Extraction uses the verified per-clip adapter unchanged, in up to 6 parallel processes of 2 threads each.

**Audio preparation.** For each selected DEV token:
- cut `[start, end]` from the session WAV;
- convert to mono 16-kHz PCM16 with a single pinned ffmpeg command (the resampler is fixed in the declaration);
- apply no trimming, padding, normalization or denoising beyond the extractor's own fixed behavior.

Each clip is verified after cutting: the segment must lie inside the session WAV, and the clip must be mono PCM16 at 16 kHz within 2 frames of `round(seconds × 16000)`. A token that fails this check, is shorter than the extractor minimum, or is rejected by the extractor is counted and reported as a failure. It is never dropped silently and never repaired.

**Outcome.** Per token:
- `k` = `responseCorrect` (rhotic votes);
- `n` = `responseTotal`;
- derhotic votes = `n − k`.

Tokens with `n = 0`, or with non-integer or out-of-range counts, are counted and reported and excluded by this pre-stated rule.

**Primary metric.** Tie-aware weighted AUROC (`multiphone_verify.weighted_binary_metrics`):
- score = model **p0 + p1** (probability that the /r/ rating is below 2);
- positive weight = derhotic votes, negative weight = rhotic votes.

This asks whether the model ranks listener-judged derhotic productions above rhotic ones. Rating scales differ (SpeechOcean 0/1/2 versus binary rhotic), so **only ranking is evaluated, with no calibration claim**.

**Secondary metrics.**
- The same analysis with score = p0.
- Weighted AP, with its vote-weighted prevalence reported.
- Spearman correlation between the p0 + p1 score and the token derhotic proportion `(n − k)/n`.

**Uncertainty.** 2,000 whole-speaker bootstrap resamples of DEV speakers (seed 20260930), NumPy linear 2.5/97.5 percentiles. Every speaker is also deleted in turn.

**Pre-stated reading.**
- The retained model "carries transferable /r/ ranking signal" only if the bootstrap **lower** AUROC endpoint exceeds .50 and more than 90% of speaker deletions stay above .50.
- AUROC ≥ .70 with a lower endpoint ≥ .60 would be called "practically meaningful ranking" for research purposes only.
- Neither reading establishes clinical accuracy, calibration or learner-feedback readiness.

**Descriptive breakdowns** (no additional tests):
- context (prevocalic / postvocalic / intervocalic);
- phase (PRE vs treatment/after);
- study;
- age year;
- listener count `n`;
- per speaker.

**Context baseline** (descriptive). A leave-one-speaker-out target-word derhotic rate, computed within DEV, shows how much ranking comes from word identity alone. The score is the pooled derhotic vote rate for the same exact word string among other speakers. If no other speaker has that word, it falls back to the pooled rate over all other speakers' tokens. It is reported beside the model and does not gate anything.

## Part 2: speech retention of the admission path (DEV)

This is the missing half of [nonspeech Part A](nonspeech-robustness-result-20260929.md).

**Selection** (from metadata, before audio):
- For each DEV speaker, take the **3** eligible tokens with the lowest SHA-256 of `percept-r-retention-v1|<folder>|<session>|<record id>`, where eligible means exactly one consonantal R, a segment of at least 0.3 s, and only phones from the extractor mapping.
- That gives about 357 natural isolated words.
- Ratings are **not** used for selection and are not part of Part 2's outcome. All tokens count as speech, whatever their rhotic quality.

**Run.** Each clip, prepared exactly as in Part 1, goes once through the unchanged admission path used in Part A:
- `multiphone_short_vad_filter.filter_report` with its pinned Silero and phone-evidence gate;
- co-primary outcomes: combined-250 and combined-100 `ratingAvailable`.

**Report.**
- Lost speech (clips *not* admitted) per policy, overall and by age, phase and study, together with Part A's false admissions.
- An exact two-sided 95% interval for each lost-speech proportion, treating clips as independent. A speaker-clustered bootstrap is shown beside it, since clips cluster by speaker.

**No threshold or policy is selected from these results.** This is the first time the nonspeech requirement can be reported with both halves.

## Failure handling and verification

- **Execution.** Each command runs once, with fresh outputs and a written failure record. There is no silent retry, exclusion or relabeling.
- **Bindings.** The declaration pins:
  - the source archive, manifest, split list, selection lists and media files (by SHA-256);
  - ffmpeg, the extractor, Silero, the gate and the bundle;
  - the protocol and the runtime.
- **Tests.** Synthetic tests cover segment cutting, prompt construction (including the single-R rule), the split, selection, the vote-weighted metrics and the bootstrap.
- **Execution guards** (added after the Fable 5.1 pre-declaration review):
  - The declaration recomputes the selections and requires equality with the pinned file.
  - Node (Part A's pinned binary), the encoder snapshot files, the old-head bundle files, the session list and the phone mapping are all pinned.
  - Unknown download-status values stop the declaration, and declaring with missing needed media requires an explicit `--allow-missing`.
  - Records are validated with placeholder votes **before** any rating is read; malformed votes are counted and excluded, never raised.
  - Each extraction report must bind its clip hash, head manifest and contract.
  - Every stage pins its upstream stage file, and the final report pins the frozen predictions.
- **Write-up.** Part 2's lost-speech counts are reported beside Part A's false admissions in the result document; the code does not merge them.
- **Audits.** Evaluation saves `evaluation/per-token.json` immediately after its sole rating read, containing joined rated records, retention outcomes, rating and structural exclusions, upstream hashes and research flags. The final report pins that artifact. `audit.py` accepts the final report and its externally recorded SHA-256, verifies saved stage/selection/split lineage and complete coverage, and independently recomputes every metric, breakdown, bootstrap, deletion, baseline, retention count and interpretation flag. It reads saved JSON only, never the corpus archive or audio, and performs no decoder, model forward, fit or retry. A parent audit is written separately. Saved-artifact verification does not independently replay inference or revalidate the original ratings against the archive.
- **Reviews.** Fable 5.1 reviews the protocol and code before declaration, and reviews the result before reporting.

## Open items before declaration

1. **Resolved: extractor constraints.** The reader requires mono PCM16 at 16 kHz, 0.1–30 s and at most 2 MB. Prompts are single-word schema-2 (orthography joined by `_`, full ARPABET), which all 4,896 selected words satisfy. Per-clip runtime is about 5 s at median (94 earlier runs), which is why the per-speaker cap exists.
2. **Resolved: ARPABET mapping.** 44,242 of 44,248 DEV eligible tokens use only symbols from the extractor mapping (`experiments/multiphone-local-features-v1.json`, 15 vowels and 24 consonants). The other 6 contain `AX0` and are excluded by a fixed rule.
3. **Resolved in code: media completeness.** The declaration binds every needed DEV session WAV from the download manifest by SHA-256. Unknown status values stop it, and missing media require an explicit `--allow-missing` and are counted as failures.
4. **Resolved in code: audio format.** Resampling uses Part A's pinned ffmpeg command with input-side `-ss`/`-to`. Each clip is checked against its segment (it must lie inside the session WAV, be mono PCM16 at 16 kHz, and be within 2 frames of `round(seconds × 16000)`), and failures are counted. If clip-shape failures turn out to be widespread, that means the tolerance is wrong, not the data. That calls for a protocol revision; the tolerance is never adjusted silently.
5. **Resolved: rating fields.** A counts-only format check found all 44,248 DEV eligible tokens well formed: integer `k` and `n`, `n ≥ 1`, `0 ≤ k ≤ n`, and `responseAve = k/n`. No distribution was inspected. The malformed-count exclusion rule stays in place but is currently empty.
6. **Resolved: compute.** The Mac CPU handles the 4,539-token sample: about 5 s per clip at median, in 6 parallel processes. Colab is not needed.

## Limits

- **Target coverage:** /r/ only; the other 22 consonants get no fresh evidence.
- **Listeners:** crowd and trained listeners are mixed, their agreement is unreported, and many tokens are recorded during treatment with clinical feedback.
- **Population:** speakers are mostly from the Northeastern US and white, and the corpus is skewed toward RSSD.
- **Units:** segment boundaries were made by research assistants or an audio-event detector; they are not verified phone boundaries.
- **Interpretation:** a positive result supports the retained model's ranking signal for /r/ on fresh children. It does not show clinical validity, calibrated probabilities or readiness for learner judgments.
