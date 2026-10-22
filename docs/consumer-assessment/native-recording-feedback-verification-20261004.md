# Native recording feedback — October 4, 2026

Status: native simulator engineering milestone verified and independently reviewed. This extends the browser recording app without completing the broader product goal.

## Use and behavior

Run `python3 scripts/consumer-app.py --port 8782` on the Mac. Build the existing CadenceLearner Debug simulator scheme. Open About → Recording feedback, or launch with `-CadenceFeedbackMode`. The separate existing research entries remain available. This new mode is compiled only for Debug simulator builds; it is not a physical-device or release feature.

Choose a word and tap Record. A recording is limited to four seconds, with review and replay available before any upload. Recording and replay do not require an age or checking permission. To use Check, select age 6–12 and explicitly allow checking on the computer, then make a new recording. Changing word, age or this permission removes the current recording. A check requires its own tap and a fresh pinned service declaration; selecting a word, starting the screen or changing settings never submits audio.

One current temporary clip remains available through review and feedback. Retake, Next word, settings changes, leaving, backgrounding and audio interruption clear it. No recording history, identity or saved results are added. The local service creates a separate temporary copy. If cleanup is uncertain, that copy may remain and checking may be blocked; native deletion and server deletion are different boundaries. Cancellation cannot recall bytes already sent to the service.

The fifteen practice prompts preserve all existing occurrences, including both baby/backpack positions and the selected banana occurrence. Whole-word recognition is separate from individual-sound assessment; treasure retains unsupported ZH target context. Feedback can report recording issues, speech detection, recognition match/mismatch/uncertainty and operational failures. It supplies neutral retry suggestions. It does not establish pronunciation correctness, a speech score, child accuracy or clinical diagnosis. The new native screen does not include an example player or camera/outline controls; those remain separate browser capabilities.

## Observed verification

| Check | Actual evidence and limits |
| --- | --- |
| Core and affected regressions | Earlier run: 53 passed (19 new core, 34 affected legacy). Final core run: 20 passed, including one added case. No skips or runtime warnings. These are separate runs, not one final 54-test execution. |
| Closed client boundary | Tests cover strict JSON shape/types/duplicates/finite values, complete source/model/policy/content pins, quality/stage prerequisites, owned bounded WAV bytes, cleanup failures and stale callbacks. Mocked transport is unit evidence. |
| Real simulator transport | Exactly one predeclared generated-silence case executed using the actual native client, fresh GET declaration and POST to localhost:8782. One passed, no skip or warning. Response reports observed silence, RMS 0, speech/word not run, non-null evidence digest and false pronunciation/diagnosis claims. No microphone, camera, playback or acoustic model invocation was requested. |
| Native temporary file | The transport test explicitly deleted the generated native WAV and asserted file absence. |
| Service cleanup | Read-only post-run audit found a fresh outer-worker diagnostic: exit 0, no timeout, cleanup confirmed, no supervision failure, no remaining attempt stages or cleanup-required/blocked markers. This is the observed normal path, not proof of crash-safe erasure. |
| Real native UI | Four focused checks cover default recording availability without age/permission, setting age and checking permission, actual centre Next changing rabbit to bread, separate About navigation and large text accessibility. Final v5: four passed, no skips/warnings. An additional focused actual Word-menu check passed once, exposing all fifteen canonical choices and selecting banana with the expected visible word and accessible value. No Record/Replay/Check action or sensor was invoked. |
| Actual visual review | Opus5.5 reviewed final normal and AccessibilityXXXL selected controls, normal initial Record visibility, normal privacy footer and About. Supplied states clear; Word label clipping is visibly fixed. This is not a full-state or screen-reader certification. |
| Formatting | Core lint completed with six style warnings (one-case-per-line/end-of-line-comment), exit 0; no functional failure inferred. |

Simulator: iPhone 17 Pro, iOS 26.5, explicit simulator `B8BC6E2C-09E9-4237-844C-3DA7EEF43279`. Native connection check used the then-current `affa8986…` view; its exact copy is preserved before later layout-only changes. The client, parser, session, catalog and test remain unchanged. Later UI builds compile their own bound view version. The silence case was not rerun for visual changes.

## Failures preserved and corrections

An initial test-only invalid Swift literal prevented compilation; zero tests ran. The corrected runs above are retained separately.

Two real four-check UI runs failed Next while three other checks passed. Screenshots confirmed the word stayed rabbit. A diagnostic probe failed before tapping because the expected text child was absent from the accessibility tree; it did not prove a hit-region cause. Moving the secondary control's frame and content shape inside its button label was the isolated source change; the unchanged centre Next regression then passed. Later action-first layout made Record visible in the normal initial viewport, and the full four-check suite passed. The first run's post-test reporting stalled and its owned runner was terminated; another diagnostic failure collector was stopped after its ownership was verified. Original results remain available; no unrelated process was stopped.

Actual large-text screenshots subsequently showed Word/Age overlap despite automated accessibility audit passing. Adaptive vertical rows resolved overlap, but the native selected Word label still clipped in v4. A custom Menu selected-value label now grows with wrapped text; final v5 actual screenshots show complete selected Word and Age text. Opus visual review clears those supplied states. The original automated passes did not establish visual correctness.

The first read-only server audit expected the wrong diagnostic envelope and raised KeyError. The corrected audit read the runtime member. No extra HTTP request or model run was made. Unused pre-run transport-plan drafts and earlier view/test versions remain archived; the executed revision-three plan is immutable.

## Evidence and remaining work

Task-local evidence: `work/consumer-feedback-20261004/native-feedback-core/` (source bindings, real result bundles and screenshots); `native-loopback/` (executed plan, actual transport and cleanup observations); `native-review/` (independent source/evidence review); `native-delivery/` (exact source supersessions and Opus design/pixel records). These paths refer to this checkout, not public app controls.

Independent core, saved-transport and final selected-control source review are clear. Final normal/XXXL supplied pixels clear Opus review. The reviewed native delivery snapshot records exact sources, receipts and preserved supersessions. Real native recording/replay/positive speech feedback, error/dark/landscape rendering, initial Record placement and privacy footer at XXXL, XXXL About, physical devices, child performance and clinical validity remain unverified. Actual tests establish normal age-nine selection and word-menu options/banana selection; Opus pixel review did not inspect every open-menu/selected state. Generated-silence transport cannot establish those facts. A guided browser multi-word summary/practice/fresh-recheck flow is planned next; it is not implemented by this native milestone. Professional review remains the finished-product handoff, per owner direction.
