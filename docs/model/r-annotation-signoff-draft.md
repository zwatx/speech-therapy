# /R/ annotation pilot signoff worksheet — draft

**Status:** decision worksheet for a qualified speech-language pathologist
(SLP) and study owner. It is not an approved protocol, a request to start
review, or permission to use labels for training. Keep any completed, signed
copy outside the source repository with the study's controlled records.

The prepared feasibility set has 40 **public SpeechOcean762 author-training**
clips from 40 speakers, balanced across corpus child/adult age bands and
aggregate rating groups. Two local reviewer packs present the same clips in
different orders under opaque IDs; neither pack contains source ratings or
model predictions. The [sample and pack record](local-training.md#blinded-r-annotation-feasibility-sample)
pins the media and source hashes. The [reviewer protocol](r-reviewer-protocol-draft.md)
and [intake contract](../../research/audio-head/ANNOTATION_INTAKE_DRAFT.md)
are provisional until the decisions below are resolved.

## Decisions required before either reviewer listens

| Decision | SLP and study-owner resolution to record in the controlled copy |
| --- | --- |
| Target task | Define whether reviewers judge an audible intended /ɹ/, a broader target-related production, or only supportable timing. Specify how accent and dialect variation are handled. |
| Presence categories | Approve or revise `expected`, `altered`, `omitted`, and `indeterminate`, with audible examples that distinguish `expected` from `altered` and `omitted` from poor capture. |
| Altered-segment interval | Decide whether `rInterval` marks an audible target-related segment for `altered`, only an audible /ɹ/, or remains `null` when the intended phone was replaced. Specify examples and rename/version the field if its meaning changes. |
| Listening procedure | Fix the playback tool/version, listening setup, allowed replay, scrubbing and speed changes, and how reviewers handle false starts, repeated target words, and speech that diverges from the prompt. Use the same rules for both independent reviewers. |
| Word and /ɹ/ boundaries | Define onset/offset conventions, whether transitions are included, and when a boundary is too uncertain to mark. Do not force an /ɹ/ interval for omission or indeterminate production. |
| Quality reasons | Approve or revise `none`, `targetWordOmitted`, `targetSoundOmitted`, `captureNoise`, `overlap`, and `timingIndeterminate`; resolve partly audible words and multiple applicable reasons. |
| Timing tolerance | Set the allowable boundary difference or overlap rule **before** comparing reviewers. Record the units and whether word and /ɹ/ intervals use different limits. |
| Timing coverage | Predeclare the minimum number or fraction of clips with intervals from **both** reviewers for each timing metric, how missing intervals count in feasibility, and whether presence categories are analyzed separately. A high overlap on a small paired subset is insufficient by itself. |
| Agreement and adjudication | Set the minimum category and timing agreement needed to proceed, define who adjudicates, and preserve both original records separately. Decide how unresolved clips are excluded or retained as uncertain. |
| Pilot outcome | Predefine what would make this 40-clip task feasible for further label collection. Do not treat the balanced sample as a population performance test. |
| Access and use | Name the authorized reviewers and local storage/retention path in the controlled record; confirm the public-source terms and exact permitted research use. Do not place patient media, identities, free text, or reviewer contact details in the export. |

If a category or required field changes, version the [export schema and
validator](../../research/audio-head/ANNOTATION_INTAKE_DRAFT.md) **before**
collection and regenerate the local pack instructions. The current locked
validator accepts exactly two independent, complete 40-record reviewer sets
and checks media hashes, structure, and interval bounds. Passing it is not
agreement or label-quality approval. The separate agreement command reports
only aggregate confusion and timing summaries; it sets no acceptance threshold.

## Controlled signoff record

The study owner should retain, outside this repository, the approved protocol
version, category examples, timing and agreement thresholds, reviewer roles,
permitted use, decision date, and signatures or equivalent documented approval.
Record any amendment before affected annotations start. If reviewers cannot
consistently locate the target, stop the target-localized training plan and
seek a better reference source. If they can, keep this pilot on the training
side and lock a separate untouched cohort before model selection or claims.
