# Selected-target listening focus — October 9

The native Debug/simulator research app now has neutral listening guidance for each of the fifteen exact selected targets. Guidance belongs to free practice and explicit guided manual practice. It does not identify a detected speech error or change a word/sound result.

## Behavior

The cue follows the complete canonical prompt, including its phone sequence, target and occurrence. The first and second B in baby and first and final K in backpack receive different cues. Banana identifies the first N, yo-yo identifies the first consonant Y using “yes,” thumb and feather use “think” and “this,” ring describes one NG without a separate G, and treasure uses “measure.” Treasure still has unsupported ZH assessment.

The existing Listen and compare section contains the focus followed by the whole-example/whole-word/own-replay instruction. It needs no age selection, check opt-in, model result or speech guess. Reading or switching the cue starts no media action. Example playback, attribution, loading/failure states and acknowledged cleanup keep their existing controls and ownership.

When example metadata is absent, the selected focus remains readable with the action “Say the whole word, then replay your try and listen for that sound.” The section says the example recording is unavailable and supplies no example Play button or fabricated credit. An actual file-loading failure is a separate existing state.

Guided cues require both manual-practice phase and agreement between the guided current prompt and feedback selection. First-round and recheck assessments and their saved results receive no listening cue. Unknown, mutated, mismatched or nil prompts cannot borrow guidance by word or ID alone.

## Verification

At final `SOURCE-v2`, all **48 distinct unit methods in five suites passed**, with zero failures, skips or expected failures. Eight new lookup tests cover all fifteen exact targets, repeated occurrences, pronunciation anchors, unsupported ZH manual guidance, all-field identity mutations, nil/unknown refusal and availability-only action changes. Forty affected existing example/session/ownership/guided tests passed at the same source.

All **four strict generated simulator UI methods passed together** at final v2, with zero failures, skips or expected failures:

| Journey | Observed result | Duration |
| --- | --- | --- |
| Real first round → early summary → treasure manual practice → full thirteen-word recheck entry; cue absent in assessments/summaries and original row/count preserved | PASS | 50.95 s |
| Ring selected in inert fixture setup; longest NG cue at XXXL, ordinary-scroll Record/Play/credits reachability, minimum 44-point controls and full viewport inclusion | PASS | 40.86 s |
| Nil example metadata, readable/hittable focus, unavailable note, no fabricated Play/credit or media started | PASS | 10.66 s |
| Unset context, real first/second-B picker changes, visible/hittable changed cue, no recording/replay/check/playback started | PASS | 28.46 s |

The original 60-second default and 90-second maximum test bounds were unchanged; there were no retry flags or relaxed assertions. The exact dedicated simulator was verified from public metadata before each serial run and returned to Shutdown afterward. Results were checked against all declared names, not just counts. Safe summary/tree exports contain the test evidence; no raw activities/attachments or OS logs were exported.

A generic **Release build passed** (exit 0), without execution. Its microphone purpose is present and camera purpose absent. All **161 bound inputs** remained unchanged throughout the final unit/UI/Release runs, including **159 native source rows and 148 Swift files**. Final native source digest: `9db5fa7c55078f3b3fc843a932ce9b7cb18982d180c293ab9bfeaab6114dd47c`. Input digest including the reviewed runner/selection: `dc77756407c03c7af02b88eaba2981222f2b2e0149e2d77586228554b5a42a34`. Existing browser predecessor/helper guards remained unchanged (18 + 50 + 10 rows); delivered browser services were not requested or modified.

Thirty-one direct task-owned PNGs are hash-bound to the final generated run. Root inspected representative cue/control viewports. An isolated authenticated Opus call reported sole `claude-opus-5-5` usage and reviewed six specified partial screenshots: no blocking issue for the feature. It did observe an existing selected-word value clipped on the left in the unchanged Word settings row. That issue is outstanding. No full page/journey, guided cue pixel, VoiceOver, dark/contrast or physical audio claim follows from this visual review.

### Preserved initial failure

At earlier source v1, 48 unit checks passed and the four-case UI run produced **3 PASS / 1 FAIL**. The safe test tree locates the failure at line 217: the ring menu item was absent during the largest-text test's wait after picker activation. The earlier root inference of exhausted page scrolling was corrected; no final menu-layout cause was established from partial pixels. V2 starts ring through the existing selected-prompt setter in the strict generated fixture, keeps the same longest-cue/control assertions/font/time bounds, and separately retains real normal-size occurrence switching. Two normal cases add cue visibility checks. V1 results and 34 direct PNGs remain preserved. **Largest-text word-menu selection remains unverified; this checkpoint does not claim to repair it.** Final results use only the complete v2 run, without pooling v1 passes.

### Source and receipts

- [Pure focus lookup](../../apps/ios-learner/Sources/Assessment/ResearchPracticeFocus.swift), [free view](../../apps/ios-learner/Sources/Assessment/ResearchFeedbackView.swift), [guided manual view](../../apps/ios-learner/Sources/Assessment/ResearchGuidedWordView.swift).
- Task evidence: `work/consumer-feedback-20261009/selected-listening-focus/` — `SOURCE-v2.json`, `INPUTS-v2.json`, `UNIT-v2-SAFE-PROOF.json`, `UI-v2-SAFE-PROOF.json`, `RELEASE-v2-EXIT.json`, `RELEASE-v2-PURPOSE.json`, exact-device Shutdown receipts, `FINAL_ROOT-v1.json`, `OPUS_VISUAL-v1.md` and preserved v1 failure evidence.
- Independent Astra source/runner preexecution and repair reviews are retained as `PREEXEC_REVIEW-v1/v2.md` and `REPAIR_SCOPE-v1.md`; source and scientific boundaries remain explicit. Final evidence/document review is recorded separately.

## Limits and scope

Selected listening instructions do not establish produced-phone correctness, /br/ versus /bw/ correction, therapeutic benefit or clinical diagnosis. Those require independent permitted produced-phone references and intended-user evidence. The browser at port 8809 and earlier delivered services remain unchanged. This native feature is Debug/simulator-only; Release compilation alone does not ship the research flow. Physical output, full VoiceOver/dark/contrast/device variation, real example service playback and clinical validity are not verified by this checkpoint.
