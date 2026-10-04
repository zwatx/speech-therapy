# Default practice sound guides — October 24, 2026

**About this sound** now gives optional, current-word instructions for canonical
initial P, M, T and D. Together with B, this covers all five default guided-review
words: ball, pig, moon, tiger and dog. These instructions are general educational
content, separate from observations of a recording. No sound-error detector,
score, individualized correction or diagnostic conclusion was added.

## Behavior and sources

P describes lip closure and a small release of air. M describes lips together for
“mmm” with nasal airflow, then continuing the word; it does not prescribe keeping
the lips open at the end of words such as mom. T/D offer tongue placement at the
ridge behind the upper front teeth, with D also mentioning voice. New guides are
text-only. Existing B illustrations and B/R/BR wording remain unchanged.

Eligibility requires the exact canonical prompt in the current session and
library, matching sound ID/symbol and initial position, and the intended first
phone in every nonempty source pronunciation variant. Forged metadata, another
session, and middle/end P/M/T/D targets do not receive these initial guides.

The adapted text credits [Catherine Anderson, *Essentials of Linguistics*, §2.6,
©2018](https://pressbooks.pub/essentialsoflinguistics/chapter/2-7-classifying-consonants/),
with a change notice and [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)
notice and link. The page's URL says 2-7; its displayed chapter is 2.6. The notice
licenses the adapted guide text, not the app. The chapter describes Canadian
English; this does not establish equivalence across all accents. An independent
[Alberta Health Services P example](https://myhealth.alberta.ca/Health/Pages/supporting-child-speech-2-sound-dev.aspx)
was checked; no AHS text, image, audio or video was reused in the new guides.
Existing R attribution remains separate. See the task's `SOURCES.md` for the source
and content boundaries. No professional review or treatment efficacy is inferred.

The disclosure stays below the recording controls. Opening it starts no media or
check. Sources uses an explicit full-row button with a minimum 44-point height and
an Expanded/Collapsed accessibility value. Closing About resets Sources. Changing
the word or guided visit resets the whole guide through the existing view identity.
Native source links now put their minimum height and rectangular hit shape inside
the label. Labels, destinations and attribution remain unchanged.

## Actual checks and retained failures

All records are in `work/default-sound-guides-20261024/`. This work used the owned
iPhone SE (3rd generation), iOS 26.2 simulator. Each SDK run ended with both the
owned and protected simulators observed Shutdown; the protected simulator was only
listed. No physical phone or app Data directory was operated on.

| Actual run | Result | Interpretation |
| --- | --- | --- |
| Combined Release unit/UI attempt | Build failure; zero tests | Release app lacked testability required by the unit target's `@testable` import. Preserved as configuration failure. |
| Separate canonical Debug unit run | 9 passed, 0 failed/skipped | All eligible initial P/M/T/D entries, all five defaults, forged metadata/variants/symbol/position/session rejection, existing B/R/BR behavior. |
| Ordinary Release UI v1 | 1 passed, 2 failed | Both new journeys failed waiting for attribution. Retained video frames visibly showed Sources still collapsed after synthesized center taps. No OS cause established. |
| Ordinary Release UI v2 | 2 passed, 1 failed | Explicit Sources button worked. Largest text passed. Normal text exposed an actual 18-point source-link accessibility frame, below the unchanged 44-point requirement. |
| Ordinary Release UI v3 | 3 passed, 0 failed/skipped | Link-label correction; both complete five-guide journeys and B/P regression passed. Official runtime-warning list empty. |

V3 normal/largest journeys took 189.985/432.329 seconds; the B/P regression took
55.502 seconds. Each full journey visits all five guides and their attribution,
license and links; P also exercises label-center Sources collapse/reopen and About
reset. It then selects only pig for practice, opens its guide, skips practice,
starts fresh recheck, verifies ball/pig start collapsed, reopens pig's correct
guide, and returns Home with the same visible history identifiers. Links are
inspected for labels, visibility, hittability and minimum dimensions, not opened.
No Record, playback, word-check or camera action is selected.

Root personally observed test parents 22611/65, 89158/0, 1689/65, 94801/65 and
36870/0 terminal. The final owned SDK process84486 closed normally after
751.354 seconds with no owner signals, remaining group rows or cleanup errors.
Final export parent51876 exited0; all three metadata/attachment stages passed.
The nine-unit model and test source bytes are unchanged by the subsequent
view-only fixes, so that result remains applicable. The final Release build
compiles the corrected view. This is not a repeat of the full R/BR UI journey.

V3 retained 104 explicit PNGs representing 90 byte-distinct images. Nine long
paragraph traces showed positive measured overlap on every move (minimum291.5
points) and each paragraph end entering the viewport. These are scroll sequences,
not a claim that long paragraphs fit one screen. Astra independently viewed all
90 byte-distinct representatives and verified all104 member hashes/sizes, with no
visual blocker found. `ACTUAL-RESULT-REVIEW.md` and `VISUAL-REVIEWED.json` record
the coverage. The largest-text recheck-pig-collapsed screenshot shows controls
above the guide; passed state assertions establish that reset, not the screenshot
alone. Accessibility label equality alone is not visibility evidence.

## Preservation and limits

The original build was first preserved in a fully verified inert archive. Later
unit/UI runs used fresh original project/DerivedData paths; no copied build
database was executed. The final run verified five preceding complete build
namespaces, containing 3380, 2347, 1923, 1124 and 1124 files. Earlier manifests,
source snapshots, failures, result bundles and exports remain intact. The final
four source bindings are in `SOURCE-BINDINGS-v3.json`. The owner uses finite
commands, sampled RSS/free-space checks and independent cleanup; synchronous
hashing is not a hard whole-parent deadline or full SDK/host-process guarantee.

No model inference, participant/holdout access, recording upload, signing/account
change, new outreach, Git publication or deployment occurred. These checks do not
establish physical audibility/capture, VoiceOver speech/order, clinical review,
pronunciation correctness or release eligibility. Native acoustic qualification,
independent sound references, measurement reliability and reviewer acceptance
remain open. The broad app goal stays active.

The next focused product improvement identified in review is direct single-word
practice from a completed guided-summary row, preserving the exact canonical
sound/position/entry and requiring confirmed cleanup before navigation. That
handoff is planned, not implemented by this guide change.
