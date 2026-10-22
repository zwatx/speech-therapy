# YAMNet silence-padding results

Completed September 27, 2026. **Surrounding silence does not reliably restore
short-word detection.** Recording length alone cannot establish adequate speech
context for the fixed YAMNet rule. No filter or learner behavior changed.

The [declared diagnostic](yamnet-padding-protocol.md) applied six exact zero-padding
variants to all 1,117 previously studied inputs. It preserved every source sample
and used the same maximum Speech score threshold of 0.5. These are dependent
processing probes on observed development recordings, not additional subjects.

| Variant | Full child utterances accepted | Word crops accepted | Initial ESC accepted | Extension ESC accepted | Newer ESC accepted |
| --- | ---: | ---: | ---: | ---: | ---: |
| Original | 1,037/1,037 | 15/17 | 0/12 | 1/24 | 0/24 |
| lead240 | 1,037/1,037 | 13/17 | 0/12 | 0/24 | 0/24 |
| tail240 | 1,037/1,037 | 15/17 | 0/12 | 1/24 | 0/24 |
| lead480 | 1,037/1,037 | 13/17 | 0/12 | 1/24 | 0/24 |
| tail480 | 1,037/1,037 | 15/17 | 1/12 | 1/24 | 1/24 |
| both480 | 1,037/1,037 | 15/17 | 1/12 | 1/24 | 1/24 |
| both960 | 1,037/1,037 | 15/17 | 1/12 | 1/24 | 1/24 |

All six variants retain the same 5,654 child positions, 52 children, 23 phones,
and 532/705/27,033 rating-0/1/2 votes. All three synthetic cases remain rejected.
Retention is not pronunciation accuracy. All age and phone support tables and
every crop score are preserved in the complete results.

Leading 240 ms loses three previously accepted crops (`010920025-word-1`,
`064010173-word-3`, `064010173-word-4`) and gains the previously rejected AND
(`030830135-word-0`). Leading 480 ms loses the latter two accepted crops without
gaining a rejected crop. A net count therefore hides different individual decisions.

Four counterexamples exceed the 0.975-second first-window length while still
failing the fixed Speech threshold:

| Crop | Original crop duration | Surrounding silence per side | Total duration | Speech score |
| --- | ---: | ---: | ---: | ---: |
| BE `001040136-word-3` | 0.285 s | 0.480 s | 1.245 s | 0.341037 |
| BE `001040136-word-3` | 0.285 s | 0.960 s | 2.205 s | 0.341037 |
| AND `030830135-word-0` | 0.445 s | 0.480 s | 1.405 s | 0.345025 |
| AND `030830135-word-0` | 0.445 s | 0.960 s | 2.365 s | 0.345025 |

Environmental admissions also change. The tail480, both480 and both960 variants
each admit chainsaw-category `1-116765-A-41.wav` and dog-category
`5-203128-A-0.wav`, both rejected originally. Lead240 removes the previous
dog-category admission `4-183992-A-0.wav`. Category labels do not establish
absence of incidental speech; these are admissions, not measured false positives.
The previously fresh panel is now observed development material. The existing
Silero/CTC filter was not run on derivatives, so no transformed conjunction
performance is claimed.

All 6,702 derivative calls, plus two original-reference replays, completed.
CPU processing took 180.44 seconds including output saves and the final original
replay, excluding model construction and the initial original replay.
Both original replays exactly matched the frozen
reference. A separate verification reconstructed all derivative waveforms,
hashes, score geometry, decisions and tables from the saved arrays. Three focused
tests and a complete synthetic orchestration passed before the actual run.
Independent post-run review is recorded separately.

This closes the recording-length shortcut as a general short-word fix. The
original universal-filter failure remains unchanged. A future speech detector
must explicitly preserve short productions and evaluate placement sensitivity.
No offsets, ensemble, threshold or alternate class were selected from these
outcomes. No training, Colab allocation, author-test access or policy promotion
occurred.

Evidence: [plan](../../research/audio-head/outputs/multiphone-20260927/yamnet-padding-v1/plan.json),
[inference freeze](../../research/audio-head/outputs/multiphone-20260927/yamnet-padding-v1/inference-freeze.json),
[complete results](../../research/audio-head/outputs/multiphone-20260927/yamnet-padding-v1/results.json),
and [source review](../../work/yamnet-padding-review-20260927/source-review.json).
