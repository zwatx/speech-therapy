# UltraSuite clinician-rating annotation audit

Completed September28,2026. **A real accessible external evaluation lead is now verified:**768 main word instances for /k/, /g/ and /r/, plus24 shared control items. Seven UXSSD children listed at ages6–10 contribute672 main instances. These are cohort ages; age at each recording session is unknown. No model was trained or evaluated.

## Actual acquired coverage

| Source | Rating rows | Unique word-instance keys | Child identifiers | Cohort-age6–12 unique keys | Within-rater extra rows |
| --- | ---: | ---: | ---: | ---: | ---: |
| UXSSD main | 864 | 768 | 8 | 672 | 96 |
| UPX shared controls | 288 | 24 | 1 | 24 | 96 |

UXSSD has108 rating rows/96 word-instance keys per child. One assigned annotator rates each child; therefore child and rater effects are confounded. UPX's24 control items are all from04M and each is rated by all eight annotators. The controls are repeated reference items for agreement, not a healthy-child baseline. The192 extra rows over960 assigned child/annotator/item pairs reconcile the paper’s overall20% repeat definition; proportions differ between main and control items. The counts match the [published sampling description](https://arxiv.org/html/2103.00324v1#S4). They do not make1,152 independent samples or establish broad error detection.

All main items remain preserved, including96 from UXSSD06M, listed at5years11months. The other seven UXSSD identifiers are listed at6–10; UPX04M at7years2months. Age joins are descriptive, not proof of age at later therapy sessions. Both datasets have a04M identifier; dataset-qualified IDs alone do not verify cross-dataset personal identity. [UXSSD table](https://ultrasuite.github.io/data/uxssd/), [UPX linked speaker table](https://ultrasuite.github.io/data/upx-spk/)

## Schema and verification

The anonymous official endpoint returned exactly50,191bytes and17,998bytes, respectively. Original bytes, SHA256 pins and acquisition commands remain local. No waveform, ultrasound, model prediction or fitted parameter was acquired or produced. Provider license and modality evidence are in the [access note](ultrasuite-human-ratings-access-20260928.md).

All headers match the declared schema. Participant is annotator1–8, not child. Target phones are g/k/r and agree with velar/rhotic class metadata. Controls occur only in the UPX CSV, so the reviewer's possible cross-file control-age join issue does not occur. No malformed utterance key, duplicate annotator/sample index or conflicting item/session/class metadata was found. Utterance-session names such asBL1 andMid_round2 differ from broader assessment labels such asBL andMid; preserve both rather than calling them corrupt.

The first route stopped because the UPX overview lacks an individual age table. Its failed source/declaration/trace remain unchanged. A separately declared fresh route binds the provider's linked speaker page, retrieved September28,2026. Four original focused tests and two fresh-route tests passed. Actual Opus5.5 reviewed the prospective plan and then the fresh source/actual declaration; it performed no execution or hashing.

The fresh calculation completed, but its literal-integer check emitted1,629 secondary-field findings because scores use decimal strings such as1.0. Those original findings remain preserved. Separate root Decimal validation confirms all primary/secondary values are mathematically integral in the expected1–5 range, and all documented default secondary values are numerically1. There are no numeric-domain/default-rule mismatches. This explains a parser representation limitation; it does not repair data or silently replace results. Any future ingestion must explicitly declare decimal numeric parsing.

Root independently rebuilt row/item/child/target/session counts, rater allocation, within-rater repeats, shared-control overlap, comment counts, sample indices, metadata conflicts and age support. Repeat agreement was not measured; only structure was audited. Actual Opus5.5 reviewed the supplied results and root numeric check with no blocking findings. It did not read CSVs, run code or recompute hashes. Its next-action advice remains subject to a fresh declaration and provider semantics; target-phone identity must not be inferred from spelling alone.

Original clinician comment text remains in source files and is not reproduced here. All declarations/source pins and the retained research bundle stayed unchanged.

## What this permits next

This covers three of23consonants and has a small SSD cohort, one rater per main child and shared repeated controls. Ages11–12 are uncovered here; the shared control items contain /g/ and /r/, with no /k/. These limitations prevent claims across the full target age/phone range.

Scores are ordinal clinician judgments made with ultrasound, audio and spectrograms; target metadata are not perceived-phone transcriptions. Conditional secondary/default counters are provenance only and must not inform prevalence, thresholds, class balance or model selection. No score-level histogram, correctness conversion, training selection or clinical/learner eligibility follows.

Ages11–12 are uncovered by these published ages; the shared controls contain /g/ and /r/, with no /k/.

The next bounded action is to verify the provider's word-instance indexing, manual reference word boundaries and exact audio occurrence/file joins, retaining child/session lineage. Phone boundaries remain forced alignments. After those joins, a separate prospective evaluation can assess the unchanged model on this narrow external resource with fixed measures; it must keep the ratings separate from training and avoid an improvised1–5to0–2 conversion. No new GPU allocation is justified for the annotation audit.

## Evidence

- [Original plan and preserved failed route](../../work/ultrasuite-annotation-audit-20260928/plan.json).
- [Exact acquired source pins](../../work/ultrasuite-annotation-audit-20260928/acquisition.json).
- [Fresh declaration](../../work/ultrasuite-annotation-audit-20260928/v2/declaration.json).
- [Actual metadata results](../../work/ultrasuite-annotation-audit-20260928/v2/results.json).
- [Actual Opus source/declaration review](../../work/ultrasuite-annotation-audit-20260928/v2/opus-review.json).
- [Independent root counts and numeric verification](../../work/ultrasuite-annotation-audit-20260928/v2/root-observation.json).
- [Additional independent metadata checks](../../work/ultrasuite-annotation-audit-20260928/v2/root-additional-observation.json).
- [Actual Opus5.5 result interpretation review](../../work/ultrasuite-annotation-audit-20260928/v2/opus-results-review.json).
