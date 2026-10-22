# UltraSuite recording and manual-word linkage

The completed audit links all 1,152 original rating rows to 792 distinct word items and 518 dataset-qualified recordings. Of those items, 786 meet the declared linkage criteria; six remain unresolved because of exact boundary overlaps in three recordings. Every row, item, interval and discrepancy is retained. These are data-linkage results, not model predictions or clinical validation.

| Dataset | Distinct word items | Rating rows | Resolved items | Unresolved items |
| --- | ---: | ---: | ---: | ---: |
| UXSSD | 768 | 864 | 762 | 6 |
| UPX shared controls | 24 | 288 | 24 | 0 |
| Total | 792 | 1,152 | 786 | 6 |

“Resolved” means that the fixed matching-word occurrence has a manual word interval, at least one provider lexicon pronunciation contains the exact target SAMPA token, and its utterance has no declared geometry anomaly. It does not establish produced-phone identity, verified phone timing, model readiness or pronunciation correctness. The source uses clinician judgments informed by audio, ultrasound and spectrograms. [UltraSuite resources](https://ultrasuite.github.io/download/), [UXSSD](https://ultrasuite.github.io/data/uxssd/), [UPX](https://ultrasuite.github.io/data/upx/).

The earlier strict audit stopped on an exact overlap and remains preserved as failed. A separate v2 audit was declared and independently reviewed before execution. It reports geometry anomalies without repairing, rounding, applying tolerance or excluding data. Any anomaly makes every item from that utterance unresolved; retained candidate intervals are provenance only.

| Recording | Previous word end | Next word start | Exact overlap | Affected items |
| --- | ---: | ---: | ---: | ---: |
| UXSSD `02M-BL1-065A` | 3.01 | 3.0099999 | 0.0000001 s | 1 |
| UXSSD `03F-Maint-058A` | 5.81 | 5.8099999 | 0.0000001 s | 3 |
| UXSSD `08M-Maint-040A` | 1.14 | 1.1399999 | 0.0000001 s | 2 |

The remaining discrepancies also stay visible. Sixteen prompt files have an embedded speaker/session header differing from the physical file identity; the audit never rewrites the source paths. Nine items have different matching-word counts in the prompt and manual reference, including three missing the requested occurrence in the prompt. Fourteen items have more than one occurrence of the target phone in a canonical lexicon pronunciation, so word linkage alone does not identify a unique phone position. All 792 items have matching manual word occurrences and at least one canonical lexicon variant containing their target; the six unresolved statuses arise from geometry.

The fixed `wordIdx` rule selects the nth occurrence of the matching word. An alternative absolute-word interpretation matches only 136 of 792 items and was recorded descriptively, never selected per item. The pre-audit UMBRELLA probe established the occurrence interpretation. Repeated rows share an item: 120 item keys have multiple rows, including the 24 controls rated by multiple clinicians. They are not 1,152 independent word samples.

This audit retains the child below the target age range. The earlier age audit identified 672 UXSSD items from seven children with cohort ages 6–10; six now have unresolved geometry, leaving 666 with the narrow linkage status above. This count is not an evaluation cohort approval. Session-specific ages remain unknown, ages 11–12 are absent, target coverage is only /g/, /k/ and /r/, and each UXSSD child has one assigned clinician. The shared UPX controls are not a healthy baseline. The provider's primary scale is ordinal 1–5, while the current model predicts a different three-level research scale; no conversion or clinical threshold has been invented.

Verification covered all 518 manual TextGrids, 792 item joins, 1,152 row links, raw time strings and labels, provider lexicon variants, prompt/listing evidence, issue identities and grouped counts. The root reconstruction used a separate regex/Decimal parser and did not import either audit or the reused L2 reader. All 1,096 declared files, the executing sources, review, declaration and retained model bundle passed the before/after checks. The v2 implementation passed 23 synthetic tests. Astra independently reviewed the source and actual declaration. A separate Opus 5.5 invocation reviewed the supplied result evidence and cleared the narrow availability/linkage interpretation, without reopening the data or running calculations.

The frozen result is `work/ultrasuite-recording-join-20260928/v2/results/result.json`, SHA-256 `ef5cbcefe728b727c7b0bdb8b43aaa63fdf82f7a4e217b52efd4833503a0e40f`. Its declaration SHA-256 is `d5a1543b898d3cc8d3d8b291a12e406950061445152ba5951d5837e5a681736e`. Independent reconstruction is preserved in `v2/root-independent-result-verification.json`; source review in `v2/astra-source-review.json`.

The text audit reads no audio and performs no model evaluation or training. A separate acquisition has downloaded and independently checked all 518 original waveforms; see [recording acquisition](ultrasuite-rated-audio-acquisition-20260928.md). The next model work needs explicit sample-rate and duration handling, canonical-notation and target-position mapping, and a prospective external comparison that respects the original ordinal ratings and repeated observations. Opus recommended an input-compatibility stage followed by a fixed-model ordinal ranking comparison before new fitting. Its suggested cropping and aggregation choices remain proposals, not an adopted evaluation protocol. No model improvement, learner feedback or clinical use follows from this audit.
