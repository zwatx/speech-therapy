# Speech Therapy

The product direction is a **consumer speech app for children ages 6–12**:
open the app, start assessment, then practice the difficulties identified. Accounts
will be optional; clinician enrollment and assignments are not the main workflow.
The name Cadence is being replaced once the owner chooses a name; no interim
name has been adopted. The [current consumer plan](.plans/2026-10-02_consumer_speech_app_direction.html)
supersedes the clinician-first product direction in the July plan.

Ordinary iPhone launch currently opens the [CAC presentation prototype](docs/consumer-assessment/cac-presentation-routine-20261025.md): a three-word sound check, per-word feedback, automatically fitted practice and a fresh recheck. Recording and replay are real; pronunciation outcomes are authored for this proof of concept. This does not establish the validated sound assessment described below.

The [Sunday, October 18 prototype target](docs/consumer-assessment/sunday-prototype-20261018.md)
requires real recording → validated multi-sound pronunciation feedback → practice
→ recheck, with model integration ahead of UI polish. The app journey and word
checks exist; the available models do not yet support the required validated
sound judgments. The requested full milestone is not realistically supported by
Sunday on current evidence. The linked checkpoint plan separates that gap from
a feasible engineering review and does not lower the acceptance bar.

The [guided same-Mac integration](docs/consumer-assessment/native-guided-model-integration-20261014.md)
now connects the Debug simulator's recording owner to the complete acoustic
feature pipeline and child research model, after explicit opt-in, known age and
a native whole-word match. Practice and fresh recheck retain separate observations;
unsupported pronunciation judgments remain disabled. Generated lifecycle tests
pass. Two permitted child-speech crops (/p/, /t/) passed native recognition and
the real model through practice/recheck; two further cases (/b/, /m/) were
uncertain and withheld. Capture hardware remains doubled in those tests.
After preserved silent-input failures, controlled BlackHole virtual input completed
T and N recording → native recognition → model → practice → recheck with six
actual recorder takes and six model calls. P/B/M/K/L withheld model requests after
native word checks. Physical-microphone behavior and pronunciation judgments remain
unvalidated. Physical output was not unmuted; the linked report distinguishes all
test routes, failures and the final audio-setting restoration scope.
The guided research flow also preserves nine distinct recording/service rejection
reasons, with actionable guidance for silence, digital-limit samples, unreadable
audio and unavailable processing. Its [focused verification](docs/consumer-assessment/native-guided-model-integration-20261014.md#cause-specific-guidance-october-15)
passed 32 generated simulator checks; these messages do not judge pronunciation.
A subsequent [service-readiness check](docs/consumer-assessment/native-guided-model-integration-20261014.md#service-readiness-and-recovery-october-15)
sends no audio and lets later fresh recordings proceed after an absent local
service recovers. All 48 focused simulator checks passed; unknown cleanup after
assessment submission still pauses model requests.
The [testable Release simulator build](docs/consumer-assessment/native-release-word-verification-20261015.md)
also matched one existing licensed public word through the bundled recognizer,
with exact cleanup confirmed. Ten Release and nine Debug checks passed after
fixing test-only compilation boundaries. A [subsequent Release guided check](docs/consumer-assessment/native-release-word-verification-20261015.md#release-guided-coordinator-continuation)
passed eight coordinator lifecycle checks and one actual ten-check journey through
review, two manually chosen practice takes and fresh recheck. Capture hardware was
doubled using the same public recording; live Release media runtime remains open.
The later [practice Next quality fix](docs/consumer-assessment/native-guided-practice-verification-20261012.md#practice-next-quality-eligibility-october-15)
passed seventeen Debug and seventeen optimized-Release-app checks with an
unoptimized test harness. A rejected latest recording now keeps Next disabled;
word recognition remains optional for completing practice.
The [ordinary Release UI continuation](docs/consumer-assessment/native-release-navigation-verification-20261015.md)
then passed two native UI journeys, including full skip-only review/practice/recheck
and largest-text setup/Close. It fixed the word picker's clipped Cancel/filter
labels and sampled Cancel tap failure. These checks use the actual Release root;
they add no speech-accuracy or live-media evidence.

A [current-source Release guided check](docs/consumer-assessment/native-release-word-verification-20261015.md#five-distinct-public-words-and-optional-practice-checks)
now passes with five distinct licensed word recordings, twelve manually requested
native checks, two saved practice entries and fresh recheck identities. Optional
practice results leave the first review frozen and do not gate participation on
a match. All twelve owned takes are cleaned up. Capture hardware and playback
remain doubled; this is app-flow verification, not pronunciation validation.

Separate [actual native playback checks](docs/consumer-assessment/native-playback-runtime-verification-20261016.md)
now pass natural completion and explicit Stop through the default AVFoundation
player, including joined cleanup acknowledgement, ownership release and file
deletion. Sampled host audio settings are preserved. A subsequent
[combined guided journey](docs/consumer-assessment/native-playback-runtime-verification-20261016.md#combined-guided-word-checks-and-replay)
now passes twelve native checks with three actual replays, frozen first-review
results, two reopened practice records and fresh recheck takes. Capture hardware
remains doubled; live microphone and mirror runtime remain open.

The completed guided summary now offers **Review these five again**, preserving
the chosen words while starting fresh observations without automatic media or
checks. Eleven coordinator/ledger checks passed on the earlier bound view.
The [repeat and search checkpoint](docs/consumer-assessment/native-guided-repeat-verification-20261016.md)
adds two passing largest-text search probes and both original compact/largest-text
repeat journeys after keeping search above scrolling results. All four current
Release methods passed once; these navigation checks add no live-media or
speech-accuracy evidence.

Home now links to all retained practice sessions when more than three exist.
The [history-access checks](docs/consumer-assessment/native-history-access-verification-20261016.md)
passed six generated native UI cases, including 100 entries at the largest text
size, Clear recovery and Back, plus an ordinary Release navigation smoke.
Forty unchanged compiled-input unit checks remain separately bound. History
stores participation metadata. The subsequent [Clear confirmation repair](docs/consumer-assessment/native-clear-confirmation-verification-20261016.md)
passes all eight history cases with complete compact/largest-text copy inspected,
plus a separate ordinary Release smoke. VoiceOver and keyboard inspection remain open.

Search and sound-library practice now refresh the existing cleanup-recovery
snapshot on dismissal. The [nested-practice checkpoint](docs/consumer-assessment/native-nested-practice-verification-20261016.md)
passes eight mirror/Close regression cases and two ordinary Release navigation
journeys without runtime warnings. The first warning-bearing run remains rejected;
failed-file dismissal and live media were not exercised in these UI checks.

Native replay rows now show per-take advice for measured silence or digital
volume limits, without changing recording eligibility or judging pronunciation.
The [recording-feedback checkpoint](docs/consumer-assessment/native-recording-feedback-verification-20261016.md)
passed 32 generated-file/lifecycle/regression unit cases, compact/largest-text
Release component journeys and a separate ordinary Release navigation smoke.
Complete advice text was inspected across 12 screenshots; live capture remains
a separate verification boundary.

A failed startup recording scan now shows a clear unavailable state with restart
instructions, while keeping safe guided navigation and Close available. The
[startup-availability checkpoint](docs/consumer-assessment/native-startup-recording-verification-20261016.md)
passed seven unit checks, four compact/largest-text Release component checks and
an ordinary production Release guided-repeat smoke. These checks do not activate
live capture or establish individual-sound correctness.

The [word-check timeout checkpoint](docs/consumer-assessment/native-word-timeout-verification-20261017.md)
distinguishes unfinished processing from “No clear match” in current takes and
guided summaries. All 21 focused simulator tests passed once; an optimized Release
app was rebuilt and installed, with recording protection and manual progress preserved.
The subsequent [guided timeout screen check](docs/consumer-assessment/native-timeout-guided-ui-verification-20261017.md)
passed both normal and largest-text journeys. Its retained-recording message avoids
promising another take during a frozen first review; six new screenshots were checked.

The [real-worker guided Close check](docs/consumer-assessment/native-word-guided-close-verification-20261017.md)
passed one simulator integration case: two Close requests waited for cancellation
of the actual bundled encoder worker before its producer removed the recording.
The subsequent [actual Close-button check](docs/consumer-assessment/native-word-guided-close-ui-verification-20261017.md)
also passed once: the guided screen stayed present during cleanup, then dismissed
after the real cancelled receipt and file deletion. Both saved screenshots were
checked. Background behavior and interruption inside prediction remain separate work.

The [hidden-feature app checkpoint](docs/model/native-hidden-app-verification-20261016.md)
now passes 13 ownership/resource unit checks and 56 unchanged numerical comparisons
through the actual app implementation on 27 generated controls plus one owned
synthetic WAV. A fresh ordinary Release app and guided-repeat smoke also pass.
This internal component adds no consumer feedback yet: the q8 mismatch, complete
native assessment and real model lifecycle/performance remain open.

The subsequent [real-prediction cancellation check](docs/model/native-hidden-lifecycle-verification-20261017.md)
passes one actual operation with three prediction returns, overlap refusal and
worker/timer joins before releasing its stopped-recording borrow. A fresh ordinary
Release guided-repeat check passes with the verification hook excluded. Cancellation
inside Core ML, Close/background handling and device performance remain unverified.

The [pre-normalization diagnostic](docs/model/native-q8-pre-normalization-verification-20261017.md)
completed four native synthetic calls, but two Mac anchor outputs differed from
the preserved baseline. Independent saved readers agree on 22/24 preservation checks;
interpretation is withheld and q8 remains disabled for learner feedback.

The [native app](apps/ios-learner/README.md) opens without an account and supports
24 consonant groups, **892 distinct words and 2,398 sound-position entries**,
word search, beginning/middle/end browsing, recording, replay, retry, and varied
short sessions and device-local participation history. Practice recordings stay temporary and local.

Ordinary practice also offers **Skip word** before a recording is kept. Skipping
starts no microphone or word check, and skipped words do not count as practiced.
Mixed rounds save only explicitly completed recorded words; all-skipped rounds
add no participation history. Guided practice retains its separate skip flow.

Intended phone placement
is verified against a pinned, licensed CMUdict; vocabulary/exercises are not a
validated treatment plan. A new Debug-only simulator speech-check lab connects a
real temporary recording to a [loopback research bridge](research/audio-head/consumer_assessment/README.md)
after explicit local-processing consent. It binds prompt occurrences, age, request
and audio bytes to an internal research outcome, then deletes native audio.
Prompt matching remains unverified, so it shows no pronunciation result.
[Coverage and content review preparation](docs/consumer-assessment/assessment-v1.md)
bind the expanded catalog; [blind /r/ confirmation](docs/consumer-assessment/r-confirmatory-preparation.md)
is a preparation draft, not a declared study. Learner assessment, speech scores,
condition findings, movement correction, exercise recommendations and account
sync remain future capabilities. Pronunciation judgments remain disabled.

Native direct practice also supports two kept tries of the current word and explicit earlier/latest listening. The [intended-sound listening cue](docs/consumer-assessment/native-listening-focus-verification-20261011.md) follows the current word and take count. Fresh unit, direct-practice, mirror and assessment interface checks and Release compilation passed in separate simulator groups. This guidance names what to listen for; it does not judge the sound produced.

Guided first review and recheck offer **Record and check** for a fresh take. After
Stop or the recording limit, an acceptable recording is checked for the word on
this device. **Record only** preserves the choice to listen and replace a take
before manually submitting its first check. Cancelled, failed or rejected capture
does not silently retry. Practice stays manual, research-model processing keeps
its explicit Check action, and a word match does not assess individual sounds.
The [October 19 checks](work/feedback-flow-next-20261019/FINAL-DELIVERY.json) passed
23 focused generated simulator tests and one separate testable Release integration
using the licensed public “bread” recording and actual bundled recognizer. Capture
hardware was doubled; the recording matched and owned file/runtime cleanup passed.
The ordinary Release build was restored and all 26 installed files matched. This
is whole-word integration evidence, not pronunciation accuracy or ordinary UI-launch evidence.

A completed non-match in ordinary or guided practice can show a short, explicitly fallible
**Word guess** from the same bundled recognition pass. It belongs only to the
current take and guided visit, and clears on replacement or departure. Guided
first-review observations remain frozen while practice and recheck use fresh takes.
Guesses stay out of practice history, frozen observations and guided summaries.
The earlier [ordinary word-guess checks](work/ordinary-word-guess-20261021/FINAL-DELIVERY.json)
passed 25 focused injected/generated simulator tests, including replay, stale-result
clearing, cancellation, final completion and normal/largest-text screens. These
checks establish software behavior; real recognition accuracy and sound judgments
remain unvalidated.

While recording, direct and guided practice show the existing microphone recorder's
live input level. The neutral bar and decibel reading appear below Stop recording;
an unavailable reading is labeled explicitly. Meter reads stop with capture
eligibility and do not alter saved-file assessment, recording limits or pronunciation
decisions. The display measures signal level, not speech detection or sound correctness.
The [generated meter checks](work/feedback-continuation-20261019/verification-v2/ACTUAL-RESULT.json)
passed all ten selected simulator tests, including stable Stop/meter layout at the
largest native text size, unavailable readings, automatic-stop gaps and cleanup
revocation. These use controlled input values and establish no physical microphone
or pronunciation-accuracy result; the original fixture-button failure is preserved.

The account-free guided flow now carries each exact entry's frozen first-review
observation into selected practice and recheck. Its [latest continuity checks](docs/consumer-assessment/native-guided-continuity-20261013.md)
contain 24 passing unit tests and 14 passing UI tests, with no failures or skips;
the original results-reader failure is preserved alongside independent collection.
The optional plain mirror is integrated in Release source. Physical media behavior
remains unverified, and word observations do not establish individual-sound correctness.
The [native sound-model interface repair](docs/model/native-input-interface-diagnostic-20261013.md)
has passed review and compilation, and two finite synthetic predictions passed
a separate saved-evidence check. The original verification timeout is preserved;
numerical parity, real-speech accuracy and learner integration remain pending.
The subsequent [hidden-feature padding check](docs/model/native-hidden-padding-verification-20261015.md)
passed all 18 generated cases against the unchanged backend encoder. This supports
preparing a new native hidden-output export; Core ML parity, the separate q8 CTC
path and complete native sound-model integration remain open.
The [new native hidden export](docs/model/native-hidden-export-result-20261015.md)
then returned all 27 generated outputs, but every case failed the unchanged
numerical limits. Cross-runtime and trace checks passed; the conversion/native
mismatch remains under investigation before sound-model integration.
The [frontend prefix diagnostic](docs/model/native-frontend-prefix-result-20261015.md)
passed all six intermediate-output comparisons on two fixed generated inputs.
The [encoder-entry probe](docs/model/native-encoder-entry-result-20261015.md)
then found the earliest exposed mismatch at positional encoding, before
attention. The [positional split](docs/model/native-positional-split-result-20261015.md)
locates the mismatch before trimming and activation, in the native convolution
output. The [explicit-padding candidate](docs/model/native-positional-padding-result-20261015.md)
retained the same failure despite passing its exported-structure gate. The
[external padding test](docs/model/native-materialized-padding-result-20261015.md)
then passed all six output comparisons on the two fixed controls. Its largest
convolution error is close to the limit. The
[integrated three-program path](docs/model/native-integrated-hidden-result-20261015.md)
now passes all 54 final comparisons on the original 27 generated cases. This establishes
Mac hidden-state parity; the later checks below cover q8 alignment, the feature/head
pipeline and iOS components. Full learner-model qualification remains pending.

The [native CTC feature kernel](docs/model/native-ctc-feature-verification-20261015.md)
now passes all29 generated cases: ten complete numerical comparisons and nineteen
expected errors. All315 Double comparisons pass, with byte-identical FP32 feature
arrays. The actual Release simulator app also builds with the new kernel. Exact
native q8 inference, composed feature/head integration and mobile runtime remain open.

The [native q8 runtime continuation](docs/model/native-q8-runtime-verification-20261015.md)
then passes all27 original generated cases: all54 full logits/log-posterior arrays
are byte-identical to the actual JavaScript backend. Swift preprocessing separately
matches all27 saved feeds exactly and passes58 validation/callback checks. The
Release simulator app builds with both pure helpers. Subsequent checks below
verify the feature/head pipeline and iOS components; full app integration remains open.

The [native feature/head continuation](docs/model/native-feature-head-verification-20261015.md)
now passes all27 generated cases and81 occurrences through alignment,1037 features,
PCA16 and both retained research heads. Seven intermediate arrays are byte-identical.
The Release app builds with the verified math helper. The iOS static runtime also
passes its API/environment smoke without booting the simulator; iOS q8 numerical
parity and complete app integration remain open. These results do not establish
pronunciation accuracy.

The [first iOS q8 model run](docs/model/native-ios-q8-result-20261015.md)
completed all27 native calls with normal cleanup, but only5 numerical cases
passed and22 failed. Matching greedy tokens did not qualify the score arrays;
this candidate remains outside feedback while the runtime difference is investigated.
The fixed prepacking control left all eight measured arrays byte-identical to
their respective baselines. The subsequent zero-prediction inspection found
byte-identical optimized graphs on both runtimes; internal execution still needs
investigation, and the numerical mismatch remains unresolved.
The instrumented checks preserve all eight saved final arrays and match both
runtimes at first-layer dequantization, post-bias, post-normalization and activation
endpoints. Four repeated-anchor checks also pass. A later four-call check now
matches at the measured final feature-extraction and encoder-entry endpoints, then
differs at encoder exit for the failing input. All twelve preservation checks pass; the difference is
narrowed to the 24 encoder blocks plus final normalization, with no unique cause or repair.
An attempted split into encoder halves was rejected because two Mac hidden-output
anchors changed slightly; it establishes no narrower location.
Separately, the [full iOS retained-head comparison](docs/model/native-ios-head-readiness-20261015.md#full-ios-feature-and-retained-head-comparison)
passes all27 generated cases/81 requested predictions on saved Mac acoustic
inputs, with unchanged numerical gates and verified process cleanup. The iOS
acoustic discrepancy and complete native app integration remain open.

The [full iOS hidden-feature chain](docs/model/native-ios-hidden-verification-20261015.md)
now passes all54 full-output/valid-prefix comparisons on27 generated cases, with
81 native predictions and verified teardown. It reuses three freshly compiled
iOS models after a preserved pre-inference copy failure. The q8 mismatch, mobile
package/performance admission and complete app model integration remain open.

A new [offline visual speech tool](research/visual-speech/README.md) extracts
visible lip geometry from permitted local video with timestamps and an explicit
audio-clock mapping. Its [dataset audit](research/visual-speech/DATASETS.md) and
[TrueDepth design](research/visual-speech/TRUEDEPTH.md) separate RGB learning from
actual sensor depth. No trained visual speech model, child validation, depth
capture, or diagnostic visual feedback is claimed. The optional native Debug
camera lab remains an engineering experiment on supported physical phones.

The existing clinician portal and consent/enrollment infrastructure are preserved
as a separate legacy foundation, with research-only silent scoring. They are not
requirements for using the consumer app. Expert annotations and content review
remain research tasks, rather than required clinician setup for consumers.

Current model work targets **ages 6–12**. The new
[expanded child research candidate](docs/model/ages-6-12-model.md) is trained and
portable, with an explicit age guard and verified export parity. It remains a
research rating predictor, with no new accuracy claim or learner judgments.
Younger ages are outside the current model milestone.

The completed [PERCEPT-R specialist study](docs/model/percept-r-binary-head-result-20261002.md)
improves mean within-child development AUROC from 0.609382 to 0.645472 on
4,534 words from 119 development children. That development result preceded the [later once-only confirmation](docs/consumer-assessment/sunday-prototype-20261018.md), which failed and consumed its test set; the separate reserve remains untouched.
This preserved /r/-only candidate has not replaced the product or established
clinical correctness; the result does not transfer to the other sounds.

The completed [model campaign](docs/model/current-multiphone-decision.md) trains
shared rating heads for 23 consonants on 14,837 canonical target positions.
It compares frozen and partially adapted speech encoders, estimated local
phonetic features, rating objectives, and age-specific fitting. The completed
19-pipeline speaker comparison shows useful probability-prediction gains, with
important sparse-error and unfamiliar-word limitations. These are corpus-rating
models, not validated child pronunciation judgments. A subsequent
[twenty-fit data-expansion study](docs/model/multiphone-position-training-report.md)
uses all 28,227 consonant occurrences. It finds useful word-slice and
within-fold gains but mixed pooled child results. A subsequent
[thirty-fit selection follow-up](docs/model/multiphone-position-selection-report.md)
improves child probability losses but still fails the rare-rating consistency
rule; no expanded model is promoted. The
[research guide](research/audio-head/README.md) locates recipes, checkpoints,
verification commands and complete reports. A [blinded SLP handoff](docs/model/slp-handoff.md)
prepares the next annotation review; no new qualified labels have been collected.
The earlier [single-/R/ pipeline](docs/model/local-training.md) and
[model development roadmap](docs/model/model-development-roadmap.md) remain
available as historical evidence and the path to prospective validation.
The [latest adult pilot development measurement](docs/data/l2-exposed-pilot-development-result-20261013.md)
resolved 31 of 48 already-exposed references and measured a 22.39% strict token
error rate on those complete references. The original strict result remains
inconclusive; this conditional development result enables no learner phone judgments.
See the [web preview instructions](apps/clinician-web/README.md#interface-preview)
to explore the redesigned workspace with fictional records.

The current product and evidence sequence is defined in the
[consumer Lab plan](.plans/2026-10-02_consumer_speech_app_direction.html). The
[July foundation plan](.plans/2026-07-10_ai_speech_therapy_app_plan.html) is historical
context; its clinician-first entry flow is superseded.

## Current implementation status

The repository is in the foundation phase. It contains:

- a resource-authorized Next.js clinician portal with tenant-scoped learner
  records, immutable consent/assent history, device enrollment, export, and
  deletion workflows, plus an audited attempt-evidence queue that exposes only
  exact-current-snapshot captures with clinician review enabled;
- clinician-visible learner-device access records with every active grant,
  bounded inactive history, consent/expiry status, explicit re-enrollment
  confirmation, a database-enforced five-grant ceiling, atomic one-time token
  replacement, durable fixed-window generation limits (10 per learner and 30
  per clinician actor per UTC hour), and immediate audited remote revocation
  that remains available at the generation limit, without exposing token or
  token-hash material;
- durable per-device, per-operation UTC-hour request budgets for assignment
  reads and audio uploads, with private `429`/`Retry-After` responses and calm
  native retry guidance; invalid-token/IP edge throttling remains a deployment
  requirement;
- an immutable clinician assignment flow for the single bounded silent
  foundation exercise: exact content hashes, consent snapshot, dose, retry cap,
  and supersession are persisted; enrolled devices fetch the current assignment
  and every upload is server-bound to its assignment/repetition/retry slot;
- a shared clinical routing domain with tested pass/analyze/abstain policy;
- a versioned JSON Schema contract with generated TypeScript and Swift clients;
- a native SwiftUI learner with microphone capture, quality coaching, retry,
  permission-denial, camera-off, Keychain enrollment, authenticated PCM upload,
  server-refreshed assignment/no-assignment/error states, dose progress, silent
  receipt, and temporary-media deletion states;
- a Postgres tenant/membership, immutable consent, append-only audit, export,
  and logical-deletion foundation with Clerk organization mapping;
- a model-independent constrained CTC phone-path scorer and analytic evaluation
  harness;
- a canonical research-only audio bake-off that rebuilds primary and reference
  candidates on one immutable label/subgroup cohort, authenticates locked-rubric
  scorecards, applies hard clinical/equity/deployment/legal gates before weighted
  ranking, and verifies signed speaker/household-disjoint owned-adaptation
  lineage; all checked-in keys and measurements are synthetic and cannot select
  a clinical model;
- a pinned, executable phoneme-CTC ONNX benchmark adapter plus consent-bound,
  short-lived learner device-session foundation;
- an off-by-default, research-consented path from accepted learner PCM through
  that benchmark adapter and constrained scorer to append-only aggregate
  ambiguous evidence, with no learner-facing probabilities or correction;
- a Debug-only on-device visual framing feasibility path with ephemeral Apple
  Vision landmarks, aggregate JSON evidence export, and a strict multi-device
  scenario evaluator; no visual consent, upload, cue classifier, or correction;
- a research-only bilabial-closure annotation contract with blinded independent
  ratings, disagreement adjudication, and inter-rater agreement reporting; no
  collected prospective labels or visual-feedback release authority;
- a synthetic prospective visual-dataset manifest harness with consent/deletion
  reauthorization, speaker/household split isolation, held-out prospective
  sites, and annotation/evidence hashes; no real participant dataset;
- a research-only selective-routing evaluator that recomputes every audio route,
  enforces exact deep-vision invocation and bypass behavior, keeps visual
  observations separate from blinded SLP decisions, and compares audio-only
  with fused explicit-cue safety, subgroup, latency, cost, and paired utility
  metrics against a pre-bound canonical run index; its
  synthetic fixtures cannot authorize feedback or change the shipped registry;
- a candidate-only, hash-bound clinical feedback catalog and research simulator with
  static SLP-evidence fields, exact route/cue grounding, two-retry/two-cue
  safeguards, per-attempt cue state, distress/stop escalation, clinician-review
  flags, a 15-minute lease, and an executable nine-scenario bounded claim audit;
  both learner and production eligibility remain hard false;
- a persistent research-only artifact registry that inherits exact consent
  lineage through feature caches, checkpoints, reports, and deployments, then
  recursively quarantines affected artifacts after supersession or deletion;
- a durable quarantine action outbox and reconciler with subject-specific
  purge/disable/retrain/re-evaluate work, idempotent leases, bounded retries,
  dead letters, receipt binding, a test-key Ed25519 verification path, and an
  append-only tenant public-key lifecycle with rotation/revocation enforcement;
  no production provider adapter, KMS/HSM custody, or private key is enabled;
- audited quarantine health monitoring and a conservative local deletion-drill
  report that can never claim production-gate eligibility;
- audited local alert snapshots that categorize actionable queue failures while
  explicitly recording that no alert delivery evidence exists;
- subject-scoped exports that reconcile retained artifact lineage and
  quarantine evidence without exposing provider secrets or other participants;
- hash-only managed-artifact bindings and append-only local reconciliation for
  object existence, digest drift, and active-versus-quarantined access state;
- research-only job authorization envelopes binding exact inputs and managed
  objects to code/config/container provenance, distinct review, and expiry;
- globally one-time execution claims with append-only operator,
  input-quarantine, and provider-drift cancellation state for runner polling;
- tenant-scoped research-runner identities with governed Ed25519 public keys,
  signed one-time claims, workload-attributed audits, and revocation enforcement;
- immutable terminal receipts that atomically bind successful outputs to
  inherited consent lineage and managed-object evidence;
- workload-signed terminal attestations with workload-attributed output,
  binding, observation, receipt, and audit evidence;
- append-only workload-signed cancellation acknowledgements bound to the exact
  claim, effective safety-precedence cancellation, and monotonic revision;
  these are explicitly workload-attested and are not independent proof that an
  external process stopped;
- append-only workload-signed heartbeats with exact claim/envelope binding,
  monotonic sequencing, cancellation-aware state, and revocation enforcement;
  they are workload assertions rather than independent process-liveness proof;
- database-clock execution leases and append-only audited liveness snapshots
  for fresh, overdue, cancellation, and terminal states, with external process
  verification and alert delivery explicitly absent;
- separate scheduler workload identities with signed, expiring, revisioned
  runner dispatch assignments bound into v2 execution claims;
- one registered-provider launch attestation per dispatch, binding the exact
  runner image and hashed process/IAM/network evidence into the execution gate
  and claim; configured-key verification is implemented, while provider-native
  credentials and a real cloud launch adapter remain absent;
- provider-signed external stop attestations bound to the launched process and
  effective cancellation are required alongside runner acknowledgement before
  launched jobs can terminalize as cancelled; real provider API termination,
  and provider-native key custody remain absent;
- separate alert-delivery workload attestations bind immutable alert-required
  liveness snapshots to canonical state and hashed channel/receipt evidence;
  no approved destination registry, real sender/provider receipt verification,
  retry/escalation workflow, or provider-native key custody exists yet;
- an automated accessibility foundation with Playwright + axe WCAG checks for
  representative clinician states and native XCTest accessibility audits for
  iOS enrollment and ready practice; manual physical-device assistive-
  technology and disabled-participant validation remains open;
- executable phase gates and architecture decisions.

It is **not** a diagnostic device, production deployment, validated clinical
system, or substitute for a speech-language pathologist. Identity/database
provider provisioning, database-enforced isolation, models validated for the
intended clinical use, and prospective clinical validation remain required
before any clinical pilot. The local research checkpoints described above do
not satisfy that validation.

The audio foundation now includes exact constrained CTC phone-path scoring and
an evaluation harness, but no acoustic checkpoint or target is clinically
approved. See `docs/model/audio-scoring.md` for the implemented boundary and the
remaining evidence gates.

The enrolled clinician-guided iOS mode verifies the device grant and current consent-bound assignment
before persisting enrollment. It uploads a clear capture only for the exact
assignment slot. The server stores derived capture metadata only and returns no
corrective feedback; the raw temporary file is removed from the device after
every upload outcome.

## Development

```bash
pnpm install
pnpm dev
pnpm test
pnpm test:a11y
pnpm typecheck
pnpm lint
pnpm build
```

The full test and build commands require Xcode, Swift, XcodeGen, and an iPhone
17 Pro simulator in addition to Node and pnpm. JavaScript-only checks remain
available as `pnpm test:js` and `pnpm build:js`.
