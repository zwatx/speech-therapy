# Native example listening and manual comparison — October 7, 2026

Implemented in the Debug/simulator **Speech practice** screen, alongside the existing word and adult bread sound checks. The broader consumer app goal remains active. **Actual native playback verification is failing in the current audio environment; this milestone is not fully verified.**

## User behavior

Play example loads only on tap. Stop/Cancel controls and Replay this try share the existing player; switching preserves the learner take, independent results and consumed check claims. Listening needs no age/context or checking opt-in. A generic canonical bread cue invites listening for b followed by r and manual comparison; it does not identify the learner's produced sound or prescribe a correction. Safe listening is independent of a service processing pause.

All15 exact prompts map to13 already licensed examples, including shared baby/backpack assets and the yo-yo/yoyo route. Treasure's generic example is available while its target assessment remains unsupported. Credits retain author, source/license, exact attribution, conversion changes, reported variety and unknown speaker age/nonclinical flags. No audio is bundled into the app target. The public bread unit-test fixture is unchanged licensed audio with its own attribution; generated UI audio has distinct metadata/hash and persistent generated labels.

The explicit public GET requires exact catalog membership, final URL/status/MIME, bounded132096-byte streaming, an overall10-second deadline, registry SHA256 and mono16k PCM/sample count. No Range, clip upload, model processing or dynamic service metadata adoption is added. The separate public temporary file has exclusive/no-follow creation, restrictive permissions and exact retained ownership after write/removal failure. More example files stay blocked until Retry example cleanup succeeds. The microphone capturer's discard is never used merely to switch listening sources. Capture/check/permission/setup/lifecycle invalidations cancel loading and revoke stale callbacks.

## Actual execution

Four root-owned simulator runs, one SE3/iOS26.5 device, preserve **62 distinct latest case results:61 passed and1 failed**. These are not one62-test suite. Full result bundles, source snapshots, logs, exact selections and summaries are in `work/consumer-feedback-20261007/native-listening-practice/`.

| Run | Observed outcome | Scope |
| --- | --- | --- |
| Unit |48passed,0failed,1skipped; exit0 |22new controlled catalog/client/session cases and26ownership regressions. Native playback opt-in was initially not forwarded; the skip is retained. |
| UI |11passed,0failed,0skipped; exit0 |6generated listening cases,3combined-result regressions,2default/large-text regressions. Two actual accessibility audits passed. No sensors, sockets or speech model in generated flows. |
| Public |1passed,1failed,0skipped; exit65 |Production bread cue/credits without playback or recording passed. Actual native public GET/hash/PCM reached the player, which failed. |
| ProductionXXXL |1passed,0failed,0skipped; exit0 |Full Play example control within the viewport, enabled/hittable/min44; no generated banner, recording or playback. |

The opt-in selected native case uses `TEST_RUNNER_CADENCE_PUBLIC_EXAMPLE_LOOPBACK=1` through xcodebuild. It downloads the actual licensed bread WAV, validates SHA `0972084b7673d4d3053ca5c73f9c2ca81ee98bb580a401061ca55bb51ee5ac6f` and8917samples, then `SystemPracticeAudioPlayer.play` throws `couldNotPlay` after30.5seconds. A separate desktop public GET returned200/17912bytes with the same hash. Neither served bytes nor generated mock playback establishes actual hearing.

The existing player is unchanged. The owned-process CoreAudio log shows the mono16kInt16 converter/output queue, then two15-second AQME output timeouts with `(0 0)` and failed starts. This supports a simulator/host audio-rendering limitation after file decoding; the precise host cause is unresolved. No global audio reset, output-setting changes, physical device/sensor use, guard relaxation, clock padding or repeated native variants were performed. Console export was unavailable; the filtered simulator log retains the actual failure. Exact public-example namespace inspection found0files remaining. The failed case stays red for future verification in a functioning output environment.

All ordinary controlled/client/session/UI checks remain distinct from that failed native boundary. There are zero human reference labels, clinical outcomes or professional approvals added by this work.

## Source and review

Prior142-row native-unified inputs matched before the new144-row archive; public engineering-pack input is archived separately. The new inventory has154source/public-input rows, including49unchanged service dependencies. Historical capsules and original fixtures are untouched.

- V1 row digest `22c0794b20eccdaed785dfee94e7f86cc7b9a1e9dfc36886461a2c2a755b6e7b`: all production input, first unit/UI runs, source review.
- V2 `77260f0aa3be76d469254d8f978cdc252c451753afa5dd7c2a027b0fcbcc1448`: README and public-credit UI/helper only; snapshot captured after command start with stable sources. Actual player failure retained.
- V3 `77a761a8eb502e2f431d980991f4c3c16ce74c4b93774657eea8cfcfc8668aa8`: only an explicit productionXXXL geometry test added before execution. Production is unchanged fromV1.

Root offline correspondence compared every asset field, hash, sample count and15prompt mappings to the fixed public registry/pack. Changed Swift strict formatting and project generation passed. Astra independently reviewed source/ownership/claims with no code blockers; source clearance is not playback or clinical clearance. Exact Opus5.5 implemented the view and reviewed10unchanged actual PNGs with no blocking visual issues.

Pixel limitations are explicit: generatedXXXL banner crops one example control; a separate productionXXXL screenshot/test shows its whole control. No single frame shows both word and sound results; actual UI assertions retain both in the hierarchy. Credit age/nonclinical lines and long text continue off-frame. Generated playing states use a mock player, not audible output. Other devices/orientations, dark mode, VoiceOver and measured contrast are not covered. Source links' visual affordance and duplicate conversion credit are minor review notes.

A Release simulator compile passed; no experimental named symbols or WAV app assets were found. Release was not executed and physical-device eligibility remains unestablished. The owned simulator was shut down; unrelated devices and owner-used app tabs/services/private recordings were not disturbed. Initial concurrent xcresult export/database materialization failed; sequential retries succeeded, with the export failure retained independently of actual test results.

## Next work

Port the current8793 **13-word guided whole-word observation → summary → manual practice → fresh recheck** flow to native with self-declared child6–12context, one media owner, immutable first results and all-attempt denominators. Retain treasure's lexical observation/unsupported target and disable child sound comparison. The one-word legacy research-lab wrapper plan is superseded because its unavailable outcomes would not add comparable useful feedback.

Native audio output/capture in a working environment, intended-child sound accuracy, independent BR/W/L/deletion truth/rights, individual correction, meaningful speech change, visual/depth utility, diagnosis, professional/participant review and release remain open. Generic licensed examples and word recognition do not complete those product goals.
