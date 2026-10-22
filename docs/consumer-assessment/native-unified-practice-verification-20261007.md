# Native unified speech practice verification — 2026-10-07

This milestone integrates truthful adult/child whole-word context and the separate adult-only bread sound comparison into the existing native DEBUG/simulator practice screen. It does not establish pronunciation accuracy or clinical diagnosis, or make the experiment eligible for a device/release build.

## Behavior

Open About → Recording feedback (screen title Speech practice). Word requests use closed schema2 context: adult or child age6–12, with no invented adult child age. Both clients pin the current unified localhost8793 service and exact source declaration. Legacy admission/assessment stays separate.

One session owns one recording, capturer and player. Choose context and check options before recording. Explicit Check word and Check sound may run in either order on the same take, retaining independent results; requests are serialized. Sound remains eligible only for an adult, the full canonical bread prompt, free practice and both fresh sound options. Context/word/options changes discard the current take. Claimed sound checks cannot be reopened on the same capture. Stale callbacks, outdated declarations/results and cross-context word replies are refused.

Known server processing or cleanup uncertainty pauses both checks while safe local replay remains available. Failed local deletion separately blocks capture/replay. Stop waiting and transport failure do not assert remote worker cleanup. Retake/end retain exact cancellation ownership and use strictly newer remote reset generations; pending controls exclude uploads. Permission requests remain serialized and session limits are truthful.

## Source and provenance

Final native source snapshot is work/consumer-feedback-20261007/native-unified-integration/FROZEN_INPUTS-v2.json:142rows (93native/project/README/localSwiftpackage plus49unchanged unified-server dependencies), row digest4339a52265b13cefd1b093e4e173d6ac28b152aae65057d621341eed517c6ecc; FINAL_CHANGE-v2.diff digestdff971ba62ea81a50d6bb8ea1268783a147f57642f8bac33574557be4af72e48. V1 snapshots/diff/review and first-test source snapshot are preserved. Only the new UI-test scroll helper/attachments changed between v1/v2; production stayed identical.

BEFORE82rows and root-before-project2rows archive superseded originals. Historical sound metadata/response fixtures remain verbatim; fresh word/sound vectors were independently generated using current Python contracts with invented replies and generated PCM. Exact bytes are compared by actual Swift client/contract tests. Prior source-bound verification capsules are retained, not rewritten as current results.

## Actual checks

All91 distinct executed cases have passing latest outcomes, zero latest failures/skips. This is across four actual runs, not one91-test run:

| Run | Executed | Passed | Failed | Skipped |
| --- | ---: | ---: | ---: | ---: |
| Initial native contracts/clients/session/UI | 88 | 85 | 3 | 0 |
| First UI scroll repair + standalone sound | 6 | 3 | 3 | 0 |
| Small-scroll sound→word flow | 1 | 1 | 0 | 0 |
| Final word→sound/context + cleanup/replay | 2 | 2 | 0 | 0 |

Final distinct scope:79 controlled unit/contract/client/context/ownership/cross-language cases, one actual native public-declaration GET, five word UI cases, three standalone sound UI cases and three combined UI cases. The first run's three requested standalone method names did not exist and were not executed/countable; corrected actual names ran in the second run. All observed xcresult runtimeWarnings arrays were empty; Xcode debugger lookup warnings remain in logs.

The first three combined flows stopped on an option enabling assertion. Actual video/events showed an offscreen tap; the next helper's full-screen swipes oscillated past the control. A smaller test-only20%-viewport gesture and explicit On assertions fixed this without changing production. Both failed bundles/videos/source versions are retained; assertions remain intact. Final actual UI tests establish word→sound and sound→word result retention, child9 context clears both results/take/options, and server cleanup pause keeps local Replay hittable while both Check buttons disappear. Default compact Record is visible; large-type setup/controls and an actual accessibility audit passed.

ACTUAL_TEST_RESULTS.json binds each actual case's latest outcome. All142 final source rows matched after tests. Only README's dated link and the new UI-test helper/attachments differ from the first test input; production source is identical. Separate Release simulator compile exited0; nm returned zero named experimental feedback symbols. This is a compile/guard check only. Owned SE3/iOS26.5 simulator132DD629-A694-4D98-A0BB-B828676DD698 was shut down successfully; no other device was modified.

Independent GPT-6 Astra source review matched142 rows, both final digests and historical/vector provenance, with no blocking findings. Exact Opus5.5 (reported modelUsage solely claude-opus-5-5, success/non-error/exit0, low effort) reviewed seven actual unchanged screenshots and found no blocking visual issues. It read pixels only, not source. Visible result hierarchy and wording distinguish recognition from experimental whole-recording BW preference. Limits remain: neither opposite-order viewport shows both results at once; the rest of the BW limitation is off-frame; XXXL image covers setup only; contrast ratios, other devices/dark mode and physical hardware were not measured. Source, pixel and actual test reviews remain distinct evidence categories.

## Evidence limits

UI result examples use explicit generated PCM and invented word/sound replies through actual contract decoding. They establish UI/ownership behavior, not physical recording, audible playback, real inference or remote cleanup. Separate native declaration GET reads public metadata only; no agent POST touches the owner-used8793 service/runtime. Release compile/symbol checks do not imply Release execution or real-device eligibility.

A separately executed sensor-denied single-context native browser diagnostic still stalled at256frames/48k (5.33ms) after6s wall time, without a MediaStream bridge/product state machine. It retained the unchanged worklet, no packet invention or padding, and closed its context. This supports an environment audio-rendering limitation; precise host cause and browser/physical capture remain unresolved. Evidence is in browser-capture-next-step/NATIVE_RESULT.json and VERIFICATION.json. Prior injected worklet packets only establish downstream processing.

Independent human BR/W/L/deletion accuracy, calibration, useful sound correction, child clinical validity and professional/real-participant review remain external evidence requirements. Reserved child raw data/refits/outreach were not performed. The broad roadmap goal remains active.
