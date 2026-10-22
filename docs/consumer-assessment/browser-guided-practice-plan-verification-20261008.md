# Browser chosen-word practice — verification, 8 October 2026

The isolated browser successor adds an explicit short practice after the first guided round. The user chooses one to three of the original thirteen words; no word is chosen automatically. A suggestion is available only for a primary first-round attempt with a complete, validated unmatched word-recognition response. That suggestion is a practice idea, not a finding about pronunciation. Uncertain, skipped, unrun and unvalidated results do not create suggestions.

The real local delivery is <http://127.0.0.1:8805/>. It has a separate source package, listener and fresh runtime. The previously delivered browser8797 and native8803 services, their private runtimes and the native compiled connection profile were not changed. Tab17 was opened in the background, observed ready on rabbit with context unset, Record idle, all three opt-ins false, camera off and no generated fixture, then marked deliverable. Service98515 and its runtime are now user-owned; no further agent requests or runtime inspection are permitted after handoff. This delivery did not execute a feedback POST or use a sensor/model.

## Behavior and boundaries

- Choices use thirteen native checkboxes. Starting requires one to three choices. A fourth unchecked choice becomes disabled until a selected choice is unticked; keyboard focus survives updates. Starting orders the words by the original roster.
- Each practice visit has fresh ownership and uses the existing Record/Stop, replay, example and optional mirror controls. Word checking is hidden and refused by the controller during this short manual sequence. The older individual Practice buttons still open their existing checked single-word flow.
- Finish requires a valid retained recording belonging to the current visit. The controller locks that exact visit/attempt/take/audio digest, clears owned media and stops the camera before acknowledging completion. Cleanup refusal aborts completion and preserves the processing pause. Finish and Next are separate actions; a finished visit cannot acquire another recording. Skip advances explicitly.
- End practice keeps the immutable first round and reports Finished, Skipped, Left unfinished and Not started. The report is held in this tab only, is explicitly not saved, and does not measure correctness or progress. Edit choices does not replace the previous report until Start. Cancelling edits retains it.
- Returning to the first summary preserves its original rows. Recheck starts the complete original thirteen-word round with fresh recordings and checks. End and clear removes the guided session. Background/context replacement discards the plan and rejects late recording callbacks.

## Source and relevant checks

The final source freeze is `work/consumer-feedback-20261008/browser-guided-practice-plan/SOURCE-v4.json`: eighteen rows comprising the seventeen-file package and its launcher. The final feature digest is `0c2dfa9cf9f40a514b7c769a94564f87ea576f2ffc1c43018256b111b093a962`, binding fifteen owned production inputs and thirty-two unchanged dependency inputs. All seventeen predecessor package rows match their before archive. State/controller/backend/model/policy/capture code did not change after the v3 retention-copy correction; v4 changes only the report's narrow-width grid and its source pins.

Actual stored checks are version-scoped and overlap. They must not be presented as one aggregate final-source suite:

| Invocation | Observed result | Scope |
| --- | --- | --- |
| REGRESSION-v1 | 46 pass, zero failures/skips | Node suite on the initial implementation, including twelve new state and six new controller cases |
| STATE-v3 | 12 pass, zero failures/skips | Selection, suggestion admission, visit identity, locked Finish acknowledgement, report/edit/recheck state |
| CONTROLLER-v3 | 7 pass, zero failures/skips | Actual controller through generated hosts; seventh case covers a track-stop exception discovered during Finish |
| CONTEXT-v2 | 14 pass | Explicit successor input through context regression VM |
| SOUND-v2 | 46 pass | Explicit successor input through sound-preview regression VM |
| SOURCE_TESTS-v1 | 9 pass | Python source inventory, package/origin and refusal checks |
| METADATA_CHECK-v2 and v4 | exit0 | Absolute worker artifact path; source metadata verification without runtime/listener/model execution |

The initial CONTEXT-v1 and SOUND-v1 defaults pointed at the predecessor. They are retained as predecessor-only results, not successor verification; `REGRESSION_SCOPE-v1.json` records that correction. The first metadata command used a relative worker artifact path and failed with `unsafe_artifact_directory` before runtime/model construction. Its log is retained. The corrected absolute-path command passed. Frozen worker imports emit four Python3.14 SyntaxWarnings about returns in finally blocks; no warning-free claim or worker modification is made.

The generated controller checks cover insufficient/cleared captures, no checking during the plan, exact cleared WAV bytes and revoked URLs, fresh Next/Skip visits, pending permissions, late cancelled streams, immutable first-round results, full recheck, cancelled edits, background/context replacement, sticky cleanup pauses and thrown camera-track cleanup. These are software tests with generated hosts, not device/media proof.

## Actual browser observations

The isolated sensor-denied helper binds only8807. Its generated graph, PCM, player events and recognizer responses are explicitly labelled invented; microphone/camera/geolocation are denied. The real production controller, renderer, request handling and response validation are used. The helper alone permits same-origin framing for exact generated HTML routes; production still sends `frame-ancestors 'none'`. Astra caught the inherited framing prohibition before launch. It was corrected only in the helper; no actual failed iframe load is claimed.

The initial wide session on featurev1 returned invented matched rabbit, unmatched bread, uncertain door, skipped baby and nine not reached. Only bread was suggested and nothing selected automatically. Selection-limit and keyboard checks passed. A generated rabbit take was finished, Next opened fresh bread, Skip opened treasure, and early End reported one Finished, one Skipped, one Left unfinished. Edit/Back preserved the report; the original first rows remained, and full recheck began fresh rabbit. End and clear succeeded. Visible counters recorded four generated captures, four track stops, four graph closures, one generated playback event, three invented word requests, zero actual speech-model calls and zero pending/expired replies. These categories are generated activity only.

On v3, a390-layout-pixel embedded session passed chooser/record/Finish/Next/Skip/report with no horizontal overflow; all thirteen choice label boxes were44pixels high. The retention text now explicitly says Finish clears tries and nothing is sent for checking during this practice. One four-second generated take was used; media counters were not retained before that narrow tab closed. No counters are inferred for that tab. A separate195-layout-pixel frame painted at CSS zoom2 had equal scrollWidth/clientWidth, but actual pixels exposed awkward fragmentation of report words/statuses. Opus5.5 identified a report-specific three-track rule overriding the existing narrow two-track layout. Root applied the proposed scoped correction.

The v4 affected-layout checks passed at390 and195 CSS layout pixels. At195 all six word/status boxes measured114.65625pixels wide and22.5pixels high, with rabbit, bread, treasure, Skipped, Left unfinished and Not started each on one line. The stress session reported zero Finished, one Skipped, one Left unfinished and one Not started. Keyboard Tab exposed all three report actions and the focused About this build control; actual screenshots retain the focus outline. Both v4 pages were ended and cleared; their observed generated media/service counters were all zero, with no recordings or invented check requests. The390 and195 conditions are embedded layout/paint checks, not real browser zoom, text-only scaling, a physical device or a comprehensive accessibility validation. Screenshots are partial scrolled iframe views, not proof of all off-screen content.

Original automation limits remain recorded: a v1 Check-button wait expired just before the four-second auto-stop, followed by an observed completed recording; no repeated capture was used to disguise that wait. In the initial stress check an incorrect age-option value and a summary-role locator reached deadlines; the actual DOM values/selectors were inspected and corrected. An attempted pre-element counter read returned empty because the helper uses output elements; the already-visible AX counter values were recorded explicitly, and the final v4 checks read the actual output identifiers.

Opus5.5's two actual review results have `is_error=false` and sole reported `claude-opus-5-5` usage. The first opened five of six initial images and identified the fragmentation. The follow-up opened all three corrected original images and found no visible blocker. It did not run the proposed layout, inspect hidden screens, measure contrast, test screen-reader behavior or verify real media. A light button fill was not attributable from the static image; the About this build outline corresponds to the observed keyboard focus. Cosmetic width/gap differences were nonblocking.

All three helper invocations exited0 after verified owned-PID SIGINT. Their tabs closed,8807 had no remaining listener and no generated temporary runtime directories remained. This proves scoped helper shutdown only, not a production crash/lifecycle guarantee. Live8805's three read-only static GETs matched the exact reviewed HTML/app/CSS bytes with no-store headers and the original production framing policy; no live feedback request was sent.

## Remaining product evidence

The previously recorded actual playback failures and stalled browser audio render clock remain unresolved. No physical capture/output, positive new ASR, target-sound accuracy, independent BR/BW/BL/deletion truth, correction efficacy, intended-child validity, repeatability, meaningful change, depth/mouth accuracy or diagnosis was established in this milestone. Reserved participant recordings were not accessed, labels/reviews/permissions were not invented, and no refit, outreach, purchase or external product deployment occurred.

The native chosen-practice milestone is separately engineering-closed. The broad app goal remains active. Fresh Lab CLI and installed fallback pulls failed on8October; the roadmap update remains a reviewed local draft and canonical/hostedv29 is not represented as newly published.
