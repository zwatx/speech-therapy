# /R/ target-interval annotation plan

Status: research planning draft with a prepared, local-only public-speech sample,
September 23, 2026. A qualified speech-language pathologist must approve the
task definition and annotation instructions before any new reference labels
are used for model training or evaluation.

## Why this is the next dependency

The public SpeechOcean762 /R/ rating probe uses a five-rater pronunciation
score but no verified time interval for the target sound. Whole-utterance
wav2vec2 and WavLM heads showed little useful MAE advantage over simple
baselines; five speaker-held-out training folds did not identify a stable
encoder winner. A separate probabilistic head improved prediction of the
corpus's rater distribution, but its mixed-rater clips remain difficult and
its whole-utterance features provide no target boundary. A constrained CTC
alignment can always place canonical `R`
somewhere, even if it was omitted or changed. In a 20-speaker training-side
pilot, 9 clips failed at least one internal support or stability check. None
of those model-derived intervals is a reference annotation.

The next question is narrow: **can qualified reviewers consistently locate and
describe the intended /ɹ/ production in the available training audio?** It is
not a diagnosis or a judgment that an individual learner should receive
feedback.

## Bounded annotation pilot

1. Lock the pinned author metadata revision, source archive SHA-256, and the
   exact-one-canonical-`R` selection. Use the 766 author-training clips only;
   keep all 759 published test clips outside this pilot.
2. Before listening, select a 40-clip feasibility sample with one clip per
   speaker: ten in each child (age ≤15) or adult (age ≥19) × aggregate `R`
   rating 2 or below 2 group. Record a fixed selection seed, source IDs, WAV
   hashes, target words, and strata in a private manifest. The balanced sample
   deliberately overrepresents low scores and cannot estimate their population
   prevalence. Avoid selecting on any model output or previously forced interval.
3. Present audio and the canonical prompt to two qualified, independent SLP
   reviewers, blinded to the corpus's rater score, model outputs, and each
   other's annotations. Present clips in independently randomized order.
4. For each clip, record the target word's audible onset/offset and an /ɹ/
   interval when supportable. Record whether the target was audibly realized as
   expected, altered, omitted, or indeterminate, plus a closed capture/label
   quality reason when an interval cannot be defended. An interval is
   **optional** when the sound is omitted or timing is indeterminate; the
   workflow must not force a plausible-looking boundary.
5. Preserve both original records. If the study owner approves an adjudication
   step, a separate qualified reviewer resolves disagreements in a new record
   without overwriting either original. Report agreement separately for
   target presence and interval timing, plus the frequency of omitted and
   indeterminate cases. The study owner and SLPs must lock acceptable timing
   tolerance and agreement criteria before scoring an independent set.

Keep the source WAV digest, target position, and opaque-ID-to-source mapping in
an access-controlled **internal provenance record**. Each reviewer export should
contain only the opaque clip and reviewer IDs, interval times in seconds,
categorical judgments, and fixed quality reasons, as the draft intake contract
specifies. Keep raw audio, names, demographics, free text, and source mapping
outside reviewer JSON. The media workspace must control access and keep
source-license attribution; the model repository should receive only approved,
de-identified labels and a separate provenance manifest after permitted use is
documented.

The source-pinned [sample recipe](../../research/audio-head/experiments/speechocean-r-annotation-sample-v1.json)
now selects exactly 40 author-training clips from 40 speakers, ten per group.
The official archive and each selected WAV have been hash-checked. Its ignored
internal manifest contains the source mapping and ratings; the separate queue
contains only opaque IDs, canonical prompts, and target positions. A local-only
preparation command copies the public WAVs into two ignored reviewer packs with
different presentation orders, opaque filenames, source attribution, and no
ratings or model outputs. Nothing has been sent to reviewers, and no new
annotation has been collected. Prompt text can still permit external corpus
lookup, so this is practical score blinding rather than guaranteed source
anonymity. See [reproduction and artifact paths](local-training.md#blinded-r-annotation-feasibility-sample).

## Decision after the pilot

If reviewers cannot identify a target interval consistently, stop the
segment-head experiment and seek a corpus with reviewed target times and
produced-phone labels. If the task is reliable, use these annotations only for
training-side method development with speaker-group separation. Lock a later,
genuinely independent cohort and thresholds before claiming localization or
pronunciation performance. Public adult/L2 ratings and a small annotation
pilot cannot establish child speech-sound-disorder validity, calibration, or
learner-feedback safety. No patient recordings or product feedback are part of
this plan.

## Draft local intake contract

A [reviewer-facing protocol draft](r-reviewer-protocol-draft.md) translates the
prepared blinded-pack fields and provisional response schema into proposed
listening steps for qualified SLP signoff.
The [draft signoff worksheet](r-annotation-signoff-draft.md) names the
category, timing, agreement, adjudication, and permitted-use decisions that
must be recorded in a controlled copy before either reviewer begins.

A [provisional intake schema and validator](../../research/audio-head/ANNOTATION_INTAKE_DRAFT.md)
now describe how a future, authorized reviewer export could be checked against
the pinned 40-clip queue and verified WAV durations. They accept only closed,
structured judgments and preserve separate records for both reviewers; omitted
or indeterminate targets need no invented /ɹ/ boundary. The source WAV digest
remains in the local provenance mapping rather than the reviewer export. No
reviewer labels have been submitted, and this draft awaits qualified SLP task
and threshold signoff before label collection or model use.

A [draft local agreement command](../../research/audio-head/ANNOTATION_INTAKE_DRAFT.md#draft-descriptive-agreement-report)
now validates that same pinned export before summarizing the two independent
reviewers. It reports categorical confusion and exact agreement, plus word and
/ɹ/ timing overlap and boundary differences only for pairs where both
reviewers supplied the relevant interval. Missing intervals retain explicit
counts rather than guessed boundaries. It has been exercised with synthetic
responses only; these descriptive figures carry no acceptance threshold,
adjudication, training approval, or clinical claim.
