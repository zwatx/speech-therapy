# Draft /R/ reviewer protocol

**Status:** provisional instructions for qualified SLP review and study-owner
signoff. No reviewer should start from this draft alone. The prepared packs
contain 40 public SpeechOcean author-training clips in different orders for
`reviewer-a` and `reviewer-b`. Each pack's `queue.json` gives an opaque
`reviewerId`, `audioFile`, canonical `targetPrompt`, `targetWord`, and zero-based
word and within-word phone positions. The prompt identifies the *intended*
/ɹ/; it does not establish what the speaker produced. The packs contain no
corpus ratings or model predictions. No audio or labels are distributed by
this document.

## Proposed independent review flow

1. After task signoff and controlled access, each qualified reviewer uses only
   their assigned pack, follows its queue order, and listens independently.
   Do not consult corpus ratings, model outputs, or the other reviewer's work.
   Use the playback tool, listening setup, replay/scrubbing rules, and
   false-start or repeated-word procedure documented at signoff; this draft
   does not choose those rules.
2. Use the prompt, target word, and positions to identify the intended word.
   Mark its audible onset and offset in seconds when defensible. Choose one
   provisional `targetPresence` value for the intended /ɹ/:
   `expected` (audible production judged consistent with the intended target),
   `altered` (audible target-related production judged different), `omitted`
   (no supportable target sound), or `indeterminate` (the available sound does
   not support that judgment). These are annotation prompts, **not** approved
   clinical or pronunciation criteria.
3. Mark an /ɹ/ interval only when its onset and offset are supportable from
   the audio. It must lie within the target-word interval if both are marked.
   Use `null` rather than guessing an interval for `omitted` or
   `indeterminate`. Either interval may be `null` when its timing cannot be
   defended. All marked times must be finite seconds between zero and the
   verified WAV duration, with start strictly before end. The study owner and
   qualified SLP must resolve **before review** whether an `altered` segment
   is eligible for `rInterval` and what that interval means; this draft does
   not decide that phonetic question.
4. Select one closed `qualityReason`: `none` when both intervals are present;
   otherwise `targetWordOmitted` (word absent; no word interval),
   `targetSoundOmitted` (word heard but intended /ɹ/ absent), `captureNoise`,
   `overlap`, or `timingIndeterminate`. An `omitted` judgment needs one of the
   two omission reasons; other judgments cannot claim an omission reason.
   The study owner should resolve ambiguous category cases at signoff before
   review begins.
5. Record only `clipId` (the queue's opaque `reviewerId`), `reviewer`,
   `targetPresence`, `wordInterval`, `rInterval`, and `qualityReason`. Keep
   source and speaker IDs, ages, original ratings, model outputs, names, free
   text, and audio bytes out of the annotation JSON. Each reviewer exports
   their own complete 40-record local JSON. The study owner can use the
   [provisional merge and intake commands](../../research/audio-head/ANNOTATION_INTAKE_DRAFT.md)
   to combine the independent sets into a complete 80-record export and check
   its structure.

This **synthetic** record illustrates the shape only; its opaque ID and times
do not refer to a prepared clip and would not pass the pinned-ID check:

```json
{
  "clipId": "0000000000000000",
  "reviewer": "reviewer-a",
  "targetPresence": "expected",
  "wordInterval": {"startSeconds": 0.7, "endSeconds": 1.4},
  "rInterval": {"startSeconds": 1.1, "endSeconds": 1.3},
  "qualityReason": "none"
}
```

Preserve the two original reviewer records separately. A third qualified
reviewer may adjudicate disagreements in a **separate** later artifact; never
overwrite either original record or place adjudication in the intake export.

Before annotation, qualified SLPs and the study owner must decide whether
these four presence categories and six quality reasons are adequate, define
the audible distinction between `expected` and `altered`, set a defensible
timing tolerance and minimum paired-interval coverage, and lock agreement
criteria, playback procedure, and handling of disputed or partly audible
words. The local validator checks structure and timing range
only. This 40-clip feasibility exercise establishes no reliability threshold,
clinical validity, learner-feedback safety, or permission to train a model.
