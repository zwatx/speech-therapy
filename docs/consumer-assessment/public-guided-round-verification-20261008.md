# Public word feedback and guided-round verification — October 8, 2026

Status: PUBLIC_GUIDED_ROUND_ENGINEERING_CLOSED. The actual fixed thirteen-input executor run, repaired decoder/state replay and independent evidence review are complete. The broad app goal remains active. `FINAL_EVIDENCE_REVIEW-v3.md` binds the exact content preserved in the task's `REVIEWED_GUIDE-v3.md`; this final guide changes that status line only.

## Actual word results

Each of the thirteen registered public clips was submitted once through the current unchanged `FeedbackExecutor.execute_feedback`, supervised offline word worker and exact full canonical prompt. All thirteen responses passed the actual wrapper validator. No browser, HTTP endpoint, capture, playback or device was involved.

| Clip | Word stage | Public guess | Executor wall time |
| --- | --- | --- | --- |
| rabbit | uncertain | null | 4.752 seconds |
| bread | model matched | bread | 3.746 seconds |
| door | model matched | door | 3.053 seconds |
| baby | model matched | baby | 3.067 seconds |
| banana | model matched | banana | 3.031 seconds |
| backpack | model matched | backpack | 3.085 seconds |
| sky | model not matched | skye | 3.089 seconds |
| vase | model matched | vase | 3.140 seconds |
| yoyo | model matched | yoyo | 3.109 seconds |
| thumb | model matched | thumb | 3.038 seconds |
| feather | model matched | feather | 3.053 seconds |
| ring | model matched | ring | 3.111 seconds |
| treasure | model matched | treasure | 3.060 seconds |

The fixed denominator remains thirteen: eleven matches, one uncertainty and one mismatch. These same clips/model/policy were previously exercised; rabbit uncertainty and sky mismatch were already known. This is current executor/envelope compatibility evidence, not new accuracy coverage or a pronunciation benchmark. “Skye” remains an unmatched lexical result under the unchanged policy; it does not establish a speech error or need for sound correction.

All responses retain eleven false claim limits. Target assessment is not performed/not validated, except treasure's ZH target, which remains unsupported. A word match does not verify a produced phone. Adult is a software request context; public speaker ages are unknown.

## Actual execution and cleanup

The reviewed command ran once in session40518, exited0, and retained thirteen planned, started, returned and terminal ledger rows. Every row has a saved original public response and confirmed cleanup. The final ledger reports no stop reason, no blocked runtime, zero owned attempt directories remaining and no executor-close failure. Per-attempt outer diagnostics report worker exit0, no timeout, cancellation or supervision failure. There was no retry, rescue, alternate clip/model/prompt, padding or policy tuning.

Executor wall times ranged from3.031 to4.752 seconds, median3.085 seconds. The outer supervisor's direct-child `wait4` maximum RSS ranged from1,104,944 to1,120,064KiB. These are observations from this batch, not controlled latency, aggregate process-tree memory, a hard memory cap or a phone benchmark. Safe outer process-tree observations may include terminal zombie states; final cleanup is recorded separately by the actual supervisor.

The run uses the existing pinned Whisper base.en/Silero readiness path and fixed offline model root. Sound3295 is loaded only for source-binding metadata; no observer or sound inference runs. Only public envelopes and bounded outer diagnostics were inspected. Private worker transcripts, posteriors and evidence files were not read by the task.

## Bound sources and rights

Task: `work/consumer-feedback-20261008/public-guided-round/`.

- Exact predeclared input plan SHA256: `c2ee9e04abfb905ef35177b769e30663b035bb795e7a1dfe9c3f7363efc5b442`.
- Reviewed executor harness SHA256: `1adba493ad2ffd13d5fb3051d9ccf7fd827478b90f5d4b3370b636a12c6fbd51`.
- Ninety-row source/public-asset digest: `58a2912a0f2a8072560bbce34dad9d6b73cc20e5daa65376019323b5528fc4d5`.
- Current browser feature SHA256: `0c2dfa9cf9f40a514b7c769a94564f87ea576f2ffc1c43018256b111b093a962`.
- Exact frozen browser app SHA256: `62e39a6c7adf5a846c16b8ff4cd2a558bae2c0c69f5417b14c1c2d1bc48702ec`.

`PREDECLARED_INPUTS.json`, original request files, `SOURCE_BEFORE.json`, frozen copies and `PUBLIC_CREDITS.json` retain every clip/prompt/attempt/request digest and complete source-specific author, license, attribution, conversion and registered local-inference permission. Retained public examples must keep those credits. No additional rights, speaker age or human phone labels are inferred.

The actual catalog validated fifteen prompt variants and thirteen unique registered public clips plus illustrations; this run selected exactly the first canonical variant for each of the thirteen words. Source guards ran before imports and around every actual attempt. The post-run `PRESERVATION-v1.json` additionally verifies all ninety source/public-asset rows and all seven prior evidence capsules, containing61/259/152/31/107/197/185 bound artifacts. No production source or prior delivery was changed.

## Decoder and state replay

The first reviewed replay stopped with exit1 because JavaScript regenerated Python float spellings (`0.0` versus `0`), changing a response hash. Archived v1 source, `REPLAY-v1.log`, causal evidence and the minimal fix remain. Astra reviewed the repair before the second replay. That second invocation also stopped with exit1: its fixed44-byte WAV-header assumption treated the rabbit LIST-chunk length26 as13samples, while the true data chunk contains16,800samples. Archived v2 source and `REPLAY-v2.log` remain. Independently reading all thirteen original public WAVs with Python's standard wave parser and a bounded RIFF metadata walk confirms mono16kHz PCM16 and every declared sample count. This read did not play audio or execute models. The reviewed v3 replay subsequently passed with exit0, using all thirteen original responses. Actual responses and models have not been modified or rerun.

The v3 replay reads original public envelopes with the exact frozen browser's strict JSON parser, word-envelope decoder and feedback interpreter, then uses controlled pure reducer events to complete the thirteen-item first round. It checks the complete ledger and request/audio/prompt/source bindings, preserves uncertainty/mismatch and suppresses guided guesses. All thirteen primary observations reach the summary: eleven matched, sky unmatched, rabbit uncertain. The optional suggestion set contains only sky, derived from its validated unmatched observation, without declaring a pronunciation problem. Repeated summary/suggestion reads preserve the first round. Starting a controlled recheck preserves that round and creates thirteen fresh unreached dispositions; no second-round responses or improvement are invented.

Controlled negative checks reject a wrong request binding and a stale reducer owner for each original response, plus one duplicate protocol key. First-round preservation and the fresh recheck are a fourth control category. These are checks within one replay, not a separately counted aggregate test suite or additional model attempts. Reducer counters show thirteen capture/check/post events supplied by the harness; actual HTTP posts, microphone captures and camera actions in this task are zero. This is not live browser/controller or physical verification.

The repaired WAV helper was separately checked against all thirteen original public files and six controlled malformed copies: wrong RIFF length, unsupported stereo, duplicate fmt, truncated data, missing data and truncated payload. That scoped inline Node check exited0; it did not execute the full replay or models. The final replay SHA256 is `a87f17f428894b9ced69d5552bdf1c2d449e6a2d27d9b13269032afe72a347ec`; its exact v1/v2 predecessors and both fixes remain archived.

## Remaining limits

Owner-used services8797/8803/8805, their runtimes and tabs were not requested, inspected or controlled. Reserved child-study recordings remain sealed. No new participants, human reviews, labels or diagnostic conclusions are created. Native playback and browser render-clock failures remain open in their original evidence.

The local roadmap draft from the preceding browser milestone remains unpublished after the recorded Lab network failures. No Lab retry or publication occurred in this task. Actual acquisition/output, independent permitted produced-phone truth, false-correction/abstention calibration, child validation, meaningful change, corrective efficacy, clinical review and release readiness remain outstanding.
