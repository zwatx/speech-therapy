# Cadence: SLP handoff

Prepared September 26, 2026. Cadence is building an immediate-start speech
practice demo for children roughly ages 2–12, initially in the iOS simulator.
The flow is prompt → record → replay → retry or continue. The native demo now
includes **24 target sounds and 72 word prompts**, all awaiting SLP content
review. Reliable pronunciation judgments remain a longer-term aim. The demo's
recording-quality messages describe capture conditions only.

The most useful SLP contributions now are a reviewed first practice pack and
an independent listening review of the prepared multi-sound audit clips.
The earlier /ɹ/ interval-annotation feasibility task remains available as a
separate study. A content review does not validate the model.

The [practice/model overlap table](practice-model-coverage.md) now records all
72 actual app word-and-target pairs against the retained research cohort.
Only 29 pairs have an all-age match and 17 have a match among ages 6–12;
matches can contain very few examples. This is an exact spelling/canonical-
phone join, not a judgment of content quality, target placement or a reason
to choose one therapy word over another. It helps identify where new,
permissioned isolated-word examples would differ from current model evidence.
All content decisions below remain pending.

## First practice pack

The [72-prompt review worksheet](practice-content-review.md) lists the exact
implemented prompt IDs, target symbols, positions, and words. Every row is
pending review, with blank decision and reviewer-note fields. Please use it
to choose a coherent first pack and record these decisions:

| Decision | What Cadence needs to implement |
| --- | --- |
| Intended users | Age/readiness bands, expected adult support, and which children or practice needs the pack is intended to serve. The full 2–12 range need not share one experience. |
| Targets and sequence | Initial sounds, word positions, and progression from easier to harder tasks; specify what the first pack should leave for later. |
| Prompts | Reviewed word/phrase examples, acceptable variants, dialect/language assumptions, picture meanings, and child-friendly instructions. |
| Reference audio | Whether a spoken example is needed, who should provide/review it, and which recordings Cadence may use. No reviewed reference-audio pack currently exists. |
| Coaching and encouragement | Approved preparation cues, retry wording, completion language, and situations where the app should offer a break or adult help. |
| Success language | Wording the demo may use before validated pronunciation assessment is available. Replay and participation can be acknowledged without asserting that a sound was correct. |

Keep child-specific information outside the content worksheet. Review the
in-app visuals and instructions with the words; generic symbols and unreviewed
vocabulary may need revision. Engineering can apply the content decisions
without adding accounts, assignments, or enrollment to the demo.

## Prepared multi-sound listening audit

A local blinded pack is ready with **15 whole utterances from five children
ages 6–12, covering 13 expected target sounds**. It uses already-studied public
corpus training audio, not recordings from Cadence users. This is a small,
purposefully selected audit of model disagreements and control examples;
it cannot estimate population accuracy or validate the intended app ages.

Start with the [reviewer guide](../../research/audio-head/outputs/slp-audit-20260926/reviewer-guide.md)
and [blank review worksheet](../../research/audio-head/outputs/slp-audit-20260926/reviewer-template.csv).
The local listening page provides whole-utterance playback, separate target
and recording-quality fields, browser drafts, and independent JSON/CSV exports.
The [coordinator guide](../../research/audio-head/outputs/slp-audit-20260926/coordinator-guide.md)
contains its local launch instructions and sampling details. These artifacts
stay in the ignored local research-output directory; this handoff does not
publish or send the audio.

The reviewer states the English reference variety, listens without seeing
model or source ratings, and records correct, incorrect, uncertain, or
unscorable for the named expected target. Heard-sound descriptions and notes
can be plain language. Recording quality is a separate decision. The displayed
target time is an automatic pointer, not a reviewed sound boundary; no audio
has been cropped or altered. Accent differences are not automatically speech
disorders. No diagnosis is requested.

Keep the coordinator scores and other reviewers' answers separate until the
independent review is exported. Preserve uncertainty and original responses;
the pack has no automatic label conversion or training importer. The first
question is which observed model errors reflect audible target differences,
acceptable variation, ambiguous location, or recording limitations. Any later
training or evaluation use needs a defined task and data split; these clips
have already participated in model selection and are not an untouched
evaluation cohort. No new qualified judgments have been entered.

This listening audit does not require the interval definitions or signoff for
the distinct /ɹ/ feasibility task below. Its guide describes its own narrower
review task.

## Prepared /ɹ/ label-feasibility pilot

The earlier /ɹ/ model predicts subjective public-corpus ratings from whole-clip
features. A new [23-target training study](multiphone-training-plan.md) now
compares pooled, attention, and partially adapted acoustic models using the
same type of ratings. Neither supplies verified produced-phone transcriptions
or validated child pronunciation judgments. Qualified reference annotation
remains useful alongside these experiments; the earlier
[model decision](current-r-decision.md) explains the /ɹ/ label gap.

The existing [40-clip plan](r-target-annotation-plan.md) uses public
SpeechOcean762 **author-training** audio with one clip per speaker. It balances
corpus child/adult groups and original rating groups; this artificial balance
cannot estimate population performance. Its corpus child band is age ≤15,
which does not establish coverage or suitability for Cadence's ages 2–12.
Two differently ordered local reviewer packs and draft intake/agreement tools
already exist. No new qualified labels have been collected.

Please review the [listening protocol](r-reviewer-protocol-draft.md) and
complete the existing [signoff worksheet](r-annotation-signoff-draft.md) with
the study owner before annotation. The consequential decisions are:

1. What `expected`, `altered`, `omitted`, and `indeterminate` mean audibly,
   including acceptable accent/dialect variation.
2. What interval to mark for an altered sound, how word and sound boundaries
   are defined, and when the right answer is an absent/uncertain interval.
3. Allowed playback/replay procedures, timing tolerance, minimum paired
   interval coverage, agreement criteria, and handling of disputed clips.
4. Who the two independent qualified reviewers and any later adjudicator are,
   and what later research use the approved labels permit.

Use the existing worksheet rather than starting a second approval process.
Keep the completed study record in its controlled location. Each reviewer
should remain blinded to source ratings, model predictions, and the other
reviewer's judgments. Preserve original reviews and adjudication separately.
The [local intake guide](../../research/audio-head/ANNOTATION_INTAKE_DRAFT.md)
describes exports and the browser/account separation required for the draft
reviewer page; this handoff does not launch or distribute that page.

If reviewers can consistently support the target judgments and intervals,
engineering can investigate target-localized features using permitted
training-side labels. If they cannot, the next decision is a better reference
source or a revised task. Representative, permissioned child/SSD evidence and
a separate untouched evaluation cohort remain necessary before calibrated
learner feedback. The capture-sensitivity study and completed acoustic training
add engineering evidence and do not replace this label work. The
[corpus candidate notes](produced-phone-corpus-candidates.md) identify additional
clinical sources to investigate once appropriate access and use terms are
established.

No reviewers have been contacted, no packs have been sent, and no child audio
has been collected as part of this handoff.
