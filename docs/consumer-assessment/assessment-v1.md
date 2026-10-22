# Consumer assessment v1 — reviewable specification

Prepared 2026-10-02. **Engineering specification / content review pending / learner pronunciation findings unavailable.** Implements the scope of the [consumer plan](../../.plans/2026-10-02_consumer_speech_app_direction.html); this document does not approve clinical content, run a model study, or declare a release.

The intended path is immediate no-account entry → a short supported assessment task → an honest result or unavailable explanation → practice. Manual practice remains available. The first engineering acceptance target is one real, traceable recording-to-internal-result attempt on a bounded pack. It need not cover every consonant or library word. An unreviewed engineering pack can test plumbing; an assessment pack offered as suitable for children needs the existing qualified content review.

## Current implementation checkpoint — October 18

The ordinary native app now offers bundled on-device whole-word recognition,
explicit unavailable/uncertain results, selected practice and fresh same-five
recheck. These word observations do not assess individual sounds. See the
[current app audit](current-app-gap-audit-20261018.md) for current evidence limits.

The Debug research assessment session already counts started/preflight-rejected
attempts, terminal outcomes/reasons and retry parent/index in session-lifetime
memory. Its ledger keeps the latest 100 rows while preserving aggregate totals
and dropped-row counts; it retains no prompt, age, audio or prediction payload.
The existing [validation workbench](assessment-validation-workbench-20261004.md)
separately implements a durable synthetic all-attempt/reference workflow. Neither
implementation is a validated consumer assessment or an actual independent study.
No new persistent assessment logging or raw-audio retention is implied.

Only participation metadata persists in ordinary practice. Its frozen first-word
observations and paired recheck are intentionally distinct from the research
all-attempt ledger. A future fixed evaluation must bind its complete attempt
roster, lineage, task/candidate versions and lawful independent references using
the existing workflow; current metadata counters alone do not provide that evidence.

## Initial implemented milestone — historical

The Debug simulator lab implements explicit explanation/local-processing opt-in,
caregiver-declared age, a pending 15-entry engineering list, real temporary native
recording, occurrence-bound loopback processing, fixed unavailable outcomes and
cleanup/cancellation guards. The service rejects exact silence/clipping under its
stated engineering rule, with no speech-detector policy selected. Prompt matching
stays unverified and no probabilities or findings reach learner UI.

Only completed **manual practice** sessions persist local participation metadata
(ID/date/sound/count, capped at 100). Research attempts were not persisted or counted in this initial
checkpoint. The later session-memory accounting implementation is described above;
this historical paragraph does not describe its current status. A real iOS loopback transport check used synthetic silence; the model parity
run used one permitted fitting fixture. Neither is prospective child or physical
microphone validation. Cold/warm latency, memory and physical-device checks remain.

## Scope and input contract

- Completed ages 6–12, explicitly supplied by caregiver; the retained loader accepts `6 <= age < 13`. Unknown age is unavailable, and younger/older ages do not inherit model eligibility. Do not infer age from voice or face.
- English with a US English dictionary reference. This is a source convention, not proof of suitability for each US dialect, multilingual learner, or accent. Intended language/reference variety and acceptable alternatives remain qualified-review decisions. Unknown or unsupported variety cannot become an articulation error.
- Prompt identity is the native catalog entry ID, target phone, literal first/interior/last phone position, source spelling, all dictionary variants, and zero-based occurrence indexes per variant. Word identity alone is insufficient. Clusters are retained: R in bread is interior; K in sky is interior. R means consonantal R; ER is outside this target. ZH is in the practice library but outside the 23-target model inventory.
- Repeated targets remain separately identifiable. Banana has two interior N phones; baby has two B phones at different positions. An entry does not establish which production was scored. Preserve a variant/occurrence mapping or abstain; do not collapse outputs into one word score without a separately fixed rule.
- Record capture ID, prompt/content version, age-scope decision, engine/model/extractor identity, elapsed duration, processing outcome and reason. Keep raw audio temporary under existing native cleanup. Research retention/upload needs a separate permissioned path; an optional account is not research consent.

## Six distinct meanings

| Layer | What the observation means | Present availability / boundary |
| --- | --- | --- |
| Duration / volume | Measured capture length and signal level; can support retry coaching | Existing recording measurements. A long/loud recording can still be noise or the wrong word; quiet speech can still be speech. No pronunciation success follows. |
| Speech presence | Whether the captured signal contains speech under a defined admission rule | Separate research filter evidence exists. Native consumer integration and intended-phone robustness are unverified. An unavailable filter is not “no speech.” |
| Prompt match | Whether the expected word/variant and target occurrence can be identified with sufficient evidence | Bundled on-device whole-word checks now exist; they do not identify a produced target phone or independently resolve every variant/occurrence. Forced alignment/CTC against a requested string does not establish that the child said it. Wrong, extra, ambiguous or unmatched words make target assessment unavailable. |
| Target research prediction | Three-category corpus-rating distribution from the retained 23-target head, or binary derhotic listener probability from the R specialist | Internal research only; separate semantics and pinned extraction required. Probability is neither percent correct nor a clinical speech score. ZH/ER unavailable. |
| Learner finding | A supported sound-specific difficulty stated to a learner/caregiver | Unavailable until reference labels, product-prompt calibration, false-correction/abstention, subgroup, content and use-rights evidence support the claim. No present condition diagnosis. |
| Participation / improvement | Participation records a completed interaction; improvement requires reliable comparable speech measurements | Counts of attempts/sessions are participation only. Speech improvement needs test/retest reliability, stable task/model identity, recording-condition controls and an agreed meaningful-change rule. |

The R head predicts `(n-k)/n` listener derhotic fraction. The retained head predicts original SpeechOcean 0/1/2 categories. Do not combine their probabilities, present a shared accuracy percentage, or convert either into diagnosis/therapy efficacy. Developer-visible results keep source semantics, eligible scope and uncertainty explicit.

## Attempt and session behavior

Each started recording belongs to one attempt; retries create a new attempt with a parent/retry index. The all-attempt denominator includes successful processing, rejected capture, cancelled capture, unsupported/unavailable requests and processing failures. A session can complete without an assessable pronunciation result. Do not silently substitute a different prompt or discard difficult recordings from reported retention.

Recommended independent state fields: capture status; speech-presence status; prompt-match status; occurrence mapping status; prediction status; learner-finding eligibility. `notRun`, `unavailable`, `failed`, `uncertain` and a negative observation are different. Early gates can leave later stages `notRun`. Each unavailable/failed state has a reason and stage; cancellation and stale callbacks cannot complete an earlier attempt or change a newer one.

| Condition | Honest state / consumer action |
| --- | --- |
| Microphone permission denied | Capture unavailable; explain how to enable it and permit manual practice. |
| Cancel/background interruption | Attempt cancelled/interrupted; cleanup temporary audio; restart as a new attempt. |
| Too short/quiet/clipped recording | Capture caution or rejection according to the actual measured rule; offer replay/retry. Do not assert poor speech. |
| Engine/service unavailable or offline dependency | Processing unavailable; recorded attempt may remain replayable temporarily; retry or continue practice. |
| Processing error/nonfinite output/wrong artifact | Processing failed; no finding; retain metadata reason and cleanup according to existing policy. |
| Speech detector not integrated | Speech presence unavailable. No assumption of speech or noise from duration/volume. |
| No speech under a validated rule | Speech presence negative; offer another recording. No target error. |
| Prompt wrong/extra/ambiguous or recognizer unavailable | Prompt match unavailable/uncertain; target finding unavailable; offer replay/retry or skip. |
| Multiple variants/occurrences unresolved | Mapping uncertain; no localized result. Preserve every candidate mapping internally. |
| Unsupported age/language/target | Scope unavailable; manual practice may remain; do not offer a substituted model result. |
| Valid research output, product evidence absent | Internal prediction available; learner finding unavailable. Participation can be acknowledged. |
| Not enough reliable attempts | Result unavailable for that target/session; show coverage, not zero correctness. |

Result wording before qualification: “Recording saved for replay,” “You finished this practice,” or “We couldn't assess this recording.” Avoid “correct,” “improved,” “speech score,” condition names, or individualized mouth/tongue correction. Preparation cues and individualized correction need separate content decisions. An engineering failure can explain technical unavailability without assigning fault to a child.

## Evidence and acceptance

[Current catalog audit](catalog-coverage.md) and [pending engineering pack](proposed-engineering-pack.md) bind the actual expanded source. The historical [72-prompt overlap](../model/practice-model-coverage.md) remains starter-only evidence. Dictionary presence/position is not labeled child-error support, isolated-word transfer, age suitability or validated practice sequence.

A real internal bridge must demonstrate pinned end-to-end PCM → extraction → target occurrence → retained distribution → optional R distribution with preserved reference parity. Its interface must resolve the older extractor `--bundle` incompatibility explicitly; the [ages-6–12 bundle](../model/ages-6-12-model.md) contains no acoustic encoders or speech filter. Measure cold/warm latency, memory and failures on permitted development fixtures and real intended phone capture; declare resampling/channel policy instead of silently changing features. Do not develop this bridge using reserved TEST recordings.

Engineering acceptance requires explicit boundary-age, repeated-target, variant, unsupported ZH/ER, malformed/nonfinite input, cancellation/stale-result, denial/interruption, quiet/short/clipping and unavailable recognition cases. Actual negative tests and parity evidence belong to integration verification. This specification supplies no simulated latency or inference receipt.

Qualified review uses [the existing SLP handoff](../model/slp-handoff.md), with the [current scoped worksheet](proposed-engineering-pack.md) as an ages-6–12 expanded-library addendum. Its historical ages 2–12 and 72 counts are superseded for this task; its independence/reference-standard process remains useful. Product release remains separate from [blind R confirmation](r-confirmatory-preparation.md) and [annotation preparation](annotation-data-preparation.md). Neither research success nor code review creates learner eligibility.
