# Browser recording cleanup — verification, 9 October 2026

The isolated successor fixes cancellation allowing a new recording before the previous microphone request, startup and audio-context closure settle. It also keeps Stop usable while recording and retains a failed capture owner so earlier tries cannot be replayed or sent for word/sound checking after cleanup fails.

The actual local delivery is <http://127.0.0.1:8809/>. The production source is `research/assessment-consumer-browser-cleanup-app`, launched by `scripts/consumer-browser-cleanup-app.py` with an explicit fresh runtime and reviewed existing public-model cache. Three static GETs matched the reviewed HTML/app/CSS with no-store and the original production framing policy. Background tab4 was observed ready on rabbit with context unset, Record idle/enabled, all three opt-ins false, camera off and no generated fixture, then marked deliverable. DELIVERY-v1 records startup and servicePID26431/session19674. The service/source/runtime are now user-owned; no further agent requests or private runtime inspection follow handoff. No feedback POST, sensor or model call occurred during delivery. The previous8805 app and its private runtime, other delivered services and the native compiled profile remain untouched.

## Behavior

- A single immutable cleanup acknowledgment joins permission, worklet setup, initial resume and teardown. Record stays disabled until all settle and the original context is confirmed closed. Late granted streams are stopped immediately.
- Successful cleanup clears only its exact owner. Failed cleanup retains that owner, original context and refused streams; its acknowledgment stays false. It does not automatically retry or permit replay, examples, word/sound checking or new capture. The existing Reload page recovery remains.
- Pending cancellation explains whether the browser's microphone request is outstanding or the recording setup is closing. Neither message promises a completion time. A cleanup failure takes priority and asks for reload. The Record/Record again label remains familiar while disabled.
- The existing recording, mirror, playback, guided practice, whole-word response validation, sound comparison, content, models and eligibility rules remain. This change does not add sound-correction or diagnosis claims.

## Source and observed checks

Evidence lives under `work/consumer-feedback-20261009/browser-capture-cleanup/`. SOURCE-v1 binds18 successor files with digest `976d642b81a6eb742d6f9a388c4d37d57c12111c013f84cf23b7645dd8ba57bf`. The actual app.js matches reviewed draft-v2 SHA `4e427d1e1a485b589fd496987ba129346850bd6613f2de2951ac938b58aeecd1`. Feature digest `73156dbae54cd752606305e7d834545f3b2e4f2dc7b5e5f4f5cfe13d2e3fa7d7` binds15 owned and32 unchanged dependency inputs.

Actual canonical results, with full commands/stdout/stderr retained in canonical-verification-v1 and canonical-correction-v2:

| Check | Result |
| --- | --- |
| Capture cancellation/ownership/failure tests |34 pass,0 fail |
| Context regression |14 pass,0 fail |
| Sound regression |46 pass,0 fail |
| Chosen-practice controller |7 pass,0 fail/skip |
| Full guided first/practice/recheck |1 pass,0 fail/skip |
| Bread practice |6 pass,0 fail/skip |
| Example playback |7 pass,0 fail/skip |
| JavaScript syntax |exit0 |
| Source inventory/origin/refusal tests |9 pass |
| Metadata-only launch |exit0; no runtime/listener/model construction |

These are separate generated software suites, not a single acoustic benchmark. The first retained bread/example6+7 results used a predecessor path. REGRESSION_SCOPE-v1 preserves and excludes them from canonical coverage; canonical-correction-v2 changes only those two test source paths and reruns the same13 assertions successfully against the actual successor. No production source or assertions changed. Final affected coverage is81 across six separate suites.

Supported installed Python3.13.14 ran source tests and metadata with warnings-as-errors. The initial default Python3.14 invocation with warnings-as-errors failed during frozen worker import, before tests, because its finally-return SyntaxWarning became a SyntaxError. That initial output was not retained as a file; PYTHON314_IMPORT_FAILURE-v2.txt preserves a repeated exact invocation under observed Python3.14.6, exit1, before tests. The harness mismatch was corrected by selecting the supported interpreter; the frozen worker was neither edited nor its warning suppressed. Earlier draft failures remain: predecessor3 pass/16 fail, initial draft19 pass; expanded v1 draft19 pass/15 fail. Astra's v1 review found that a false acknowledgment cleared the failed-owner gate; v2 repairs it. REVIEW-v2 is clear for final canonical verification.

## Generated browser observations

The exact helper8811 uses actual successor UI/controller and generated media/graph/player events with invented service replies. Permissions policy denies actual microphone, camera and geolocation; no actual sensors, output or acoustic model ran. HELPER_INPUTS-v1 binds10 helper/fixture/metadata inputs. BROWSER_PROOF-v1 records11 observation checkpoints, not11 independent automated cases:

- Cancel during pending permission and context close kept Record disabled. Granting the late request immediately stopped its generated stream, changed the status to closing setup and kept Record disabled. Finishing close enabled a fresh recording.
- Refusing close before permission returned displayed reload recovery. A later grant stopped its stream but did not re-enable recording or example playback.
- Reload restored a fresh idle page. One generated4.0-second auto-stopped try reached the existing word check and received the deliberately invented no-speech reply. A second try stopped through the actual Stop control and retained0.4seconds; Stop was observed enabled during recording.
- With those tries retained, pending close blocked new recording and replay. Failed close kept Record again, latest replay and Check this try disabled. After reload, counters restarted; before reload the first sequence had2 generated streams stopped and1 successful graph closure plus1 refused closure. The final sequence had3 streams stopped,2 graphs closed and1 refused closure. These are separate counter periods, not pooled totals.

The initial post-reload automation raced loading and matched two hidden age selects. No selection succeeded; a fresh ready snapshot resolved the locator. No timing assertion or production control was changed to accommodate automation.

The three reviewed screenshots are partial desktop viewports: browser-permission-pending-v1.jpg, browser-close-pending-v2.jpg and browser-close-failed-v1.jpg. They show pending status or the existing failure banner, not all off-screen content. Opus's exact reported model identity/result and limitations are retained in opus-visual-result-v1.json and OPUS_VISUAL-v1.md. No comprehensive mobile, screen-reader, contrast or real-media claim follows from them.

The owned tab closed; exact helper PID24944/command was checked before SIGINT. Its invocation exited0,8811 became bindable and its generated temporary runtime was removed. FINAL_GUARD-v1 confirms18 successor,50 predecessor/dependency,10 helper and157 native rows unchanged. This is helper shutdown evidence, not a production crash/deletion guarantee.

## Remaining product evidence

Real acquisition/output failures remain unresolved. This milestone establishes software ownership and UI handling under generated conditions. It does not establish physical audibility, new positive ASR, independent BR/BW/BL/deletion correctness, intended-child calibration, false-correction rate, correction efficacy, repeatability, meaningful change, mouth/depth accuracy or clinical diagnosis. No participant recordings, new corpus rights, consent, labels, professional reviews or outcomes were invented. The broad app goal remains active.
