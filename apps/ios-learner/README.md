# Cadence iOS learner

Ordinary launch opens the [Congressional App Challenge prototype](../../docs/consumer-assessment/cac-presentation-routine-20261025.md): record three sound-check words, see per-word sound feedback, follow the automatically selected practice, then record a fresh recheck. The current BOAT → RABBIT → SUN scenario has authored outcomes; it does not measure pronunciation or infer a diagnosis. Recording, replay and cleanup are real and local. The word screen includes a live ARKit/TrueDepth face preview during recording, replay and feedback. Start sound check opens the camera; audio starts only after Record. Hide switches to audio-only practice. Facial movement does not score pronunciation. The older practice routes remain available only through explicit Debug legacy entry flags.

Current product direction (2026-10-02): a consumer app for children ages6–12,
optional account, immediate assessment leading to personalized practice. Clinician
enrollment is not the consumer workflow. Cadence is a rejected name pending a real
replacement; no placeholder name has been adopted. The current app implements
local practice, participation history, an explicit on-device word check and a Debug-only simulator research check. Validated sound assessment and corrective feedback remain unfinished. See the [consumer plan](../../.plans/2026-10-02_consumer_speech_app_direction.html).

In guided first review and recheck, **Record and check** records a fresh take and
checks its word on-device after Stop or the four-second recording limit, provided
the existing capture and cleanup checks pass. Before the first submitted check,
**Record and check another try** explicitly replaces a kept take and checks the
new recording when those same checks pass. It preserves the existing two-take
limit and waits for any required older-file removal before recording.
**Record only** lets the learner
listen and replace a take before choosing its first check. Practice and direct
recording retain manual checking. With research processing enabled, recording and
the explicit research Check remain separate actions. Combined capture intent is
discarded on interruption, cancellation, failure or visit change; returning or
recovering cleanup never restarts it. Existing word observations, first-result
freezing and explicit navigation are unchanged.

After recheck, each word in **Your word observations** offers **Practice {word}**.
This opens a fresh one-word session for that exact sound and position, including
R in bread rather than B in bread. The review ends after confirmed media/file
cleanup; the screen explains that its observations will not carry over. Failed
cleanup retains the summary and recovery controls, and recovery alone opens
nothing. A fresh explicit tap is required. Healthy **Review these five again**
keeps its existing behavior; an owner already stopped by this new departure path
is replaced with a fresh owner for the same five words. Opening practice starts
no media or check and adds no participation history. See the
[review-to-practice verification](../../docs/consumer-assessment/native-guided-practice-handoff-verification-20261024.md)
for the actual normal/largest-text journeys, retained failures and limits.

Today’s weekday and About use separate rows at accessibility text sizes. About
has a fixed Done header with a minimum 44-point label target and separately
allocated content space. Both current-source ordinary Release journeys pass at
normal/largest text, including the complete initial About title, dismissal and
media-free practice entry. See [Home/About verification](../../docs/consumer-assessment/native-home-header-verification-20261024.md)
for the retained failures, actual screenshots and named simulator demo candidate.
This does not qualify historical contrast failures, live media or sound assessment.

October 19 verification passed 23 focused generated tests, including complete guided
journeys at compact and native-largest text. A separate isolated testable Release
check matched the licensed public “bread” recording through the actual bundled
recognizer and confirmed actual runtime release and recording deletion. Capture
hardware was doubled. The ordinary Release build was restored and all 26 installed
files matched; ordinary UI launch and individual-sound accuracy are not established.
See the [delivery evidence](../../work/feedback-flow-next-20261019/FINAL-DELIVERY.json).

The Word check section now stays above playback while checking and after a result.
Initial-review check status lives inside that section; frozen first-review context
remains above the prompt during practice and recheck. This avoids changing header
height when the initial result arrives, while retaining native text growth and
scrolling. Three focused generated checks passed, including held-to-result first
review and recheck at normal and largest accessibility text sizes. The ordinary
Release app was installed and all 26 files matched. See the [stable feedback delivery](../../work/stable-feedback-slot-20261019/DELIVERY.md)
for images, preserved failure and limits.

The historical Debug **Record with feedback** simulator factory selects the reviewed
browser word-guess contract through a separately run local service on8803. Word,
sound and public-example clients all use that same closed compiled profile;
returned metadata cannot choose an endpoint or replace trusted source hashes.
Start the unchanged `scripts/consumer-browser-guess-app.py` launcher with8803,
an explicit fresh runtime, reviewed cache and exact reviewed source/worker inputs.
Do not reuse a browser session's private runtime for verification. Historical
word-guess client defaults remain8795, and guided/standalone defaults remain8793.
`ResearchBrowserWordGuessLoopbackTests` is an explicit one-shot generated-silence
transport check, skipped by default. It loads public bytes but never plays,
captures or runs a sound model. These routes remain Debug-and-simulator only;
physical phones cannot reach the Mac through127.0.0.1. The default direct practice
and review/practice/recheck flow use the bundled native recognizer described below.

The expanded library has **892 distinct words and 2,398 sound-position entries**.
Sound rows open beginning/middle/end lists; search starts a short session at the
selected word. Sessions proceed forward for up to three words and can continue
with new words; they do not wrap at the end of a list. The home starter remains
ball, boat, bee. Phone placement is checked across the source pronunciation
variants, including consonant clusters; ER is not treated as consonantal R.
CMUdict copyright and terms are available in About → Dictionary license.
Provenance, source commit/hash and reproduction are in [content documentation](../../docs/content/practice-library-provenance.md).

**About this sound** offers an optional explanation and original lip illustration
for canonical B-at-the-start words, including ball, boat and bee. R-at-the-start
words and R after initial B, such as R in bread, offer a tongue-placement option
and acknowledge different ways to make R. Canonical initial P/M/T/D words now
offer short text-only instructions, so all five default review words have guides.
The R guide uses US-English targets; other R contexts and sounds have no guide yet.
Choosing B in bread keeps the B
explanation; choosing R offers the BR explanation. Eligibility follows every
canonical source pronunciation, including clusters, rather than spelling alone.

The guide stays below the recording controls and opens without starting media
or checking a recording. A new word or guided visit starts collapsed. This is
general information about the chosen sound, independent of word-check results;
it does not identify a sound error or prescribe a tongue shape. References are
inside the explanation. Sources opens from a full-row button and resets when
About closes; source-link labels have a minimum 44-point touch height. The adapted
B/P/M/T/D text is offered under CC BY-SA 4.0; that notice covers the guide text,
not the app. See the [B source record](../../work/selected-sound-guide-20261023/SOURCES.md) and
[R source and content boundary](../../work/r-practice-guide-20261023/SOURCES.md).
The [default-guide verification report](../../docs/consumer-assessment/native-default-sound-guide-verification-20261024.md)
records the new sources, preserved failures and actual normal/largest-text Release checks.

## Direct practice demo

After stopping a recording, **Check words in this try** (or **Check words in latest
try** when keeping two takes) compares the recognizer's
independent English transcription with the selected word. The default checker uses
the bundled English Whisper model through Core ML for short recordings, on iOS 17
or later. Checking does not download assets, ask for a speaker's age, upload audio,
contact the Mac service, start recording or play audio. Unavailable or rejected
resources leave recording and listening usable. A recognized word does not establish correct individual
sounds; a mismatch does not identify a pronunciation error.
The full checking requirements are available under **About word checks**. Replay
and **Record another try** remain together before optional explanatory guidance.

Only the latest stopped take can be checked. Its observation stays in memory and
is cleared by another recording or a transition. Recording, playback and navigation
wait while a check uses the file. **Cancel check** requests cancellation; cleanup
is confirmed only after the recognition worker and its deadline task have finished. Close,
background and interruption revoke results and wait for that same cleanup before
removing recordings. An unconfirmed cleanup keeps the file and blocks new media
actions rather than reporting successful disposal. The full recognition transcript
is not retained. A clean completed non-match can carry one validated, short
**Word guess for this try** from that same recognition pass. The guess may be wrong
and does not assess individual sounds. It appears only for the exact latest kept
take and current guided visit, and clears on replacement, departure or interruption.
Missing or rejected alternatives leave the existing word observation intact.

Guided first-review and recheck submissions remain frozen; showing a guess does
not enable another recording or check in that submitted visit. Practice can show a
fresh current-try guess alongside its unchanged first-review context. Guessed text
stays out of settlement events, frozen observations, paired summaries, saved word
selections and participation history.

Guided practice requires an acceptable latest recording before finishing that
practice word. If its length or volume prevents completion, the current recording
guidance appears above **Record another try**, even when the optional word check
matches. A fresh acceptable manual take clears the requirement; checking the word
again is optional. **Skip this word** remains available. Ordinary practice retains
its advisory recording tips and existing continuation rules.

The app opens directly to local practice, without an account, enrollment, or
assignment. Choose one of 24 English consonant groups (892 distinct words), record a
word, replay it, retry, and continue through up to three words, then practice more. Recording length and
volume tips are advisory; completing a session is participation, not a
pronunciation result. The vocabulary is unreviewed demo content. Use the
[earlier 72-prompt SLP worksheet](../../docs/model/practice-content-review.md) to review the original starters,
pictures, dialect assumptions, readiness, and possible reference audio.

Before keeping a recording, ordinary practice offers **Skip word** to move on
without requesting microphone access or starting media or a word check. Skip is
unavailable during recording, a pending permission/check, other audio, or unresolved
cleanup; it never discards a retained take. Skip waits for any owned camera to stop
before the next word opens. A denied or failed recording with no kept take can also be
skipped. For a kept recording, use the existing Next/Finish or delete-and-retry
actions instead.

Round progress counts word positions separately from participation. The completion
screen distinguishes practiced and skipped words; history counts only recorded
words explicitly continued. An all-skipped round adds no history entry or save
retry. A mixed round retains the same completion identity and actual practiced
count for save retries. Restart and Practice more begin fresh counts. Guided
review/practice/recheck retains its separate existing Skip behavior.

The interface follows the system's light or dark appearance with a monochrome
palette, flat sound rows, serif headings, and simple text controls. It uses no
cards, all-caps labels, eyebrows, or status lights.

Audio is recorded only after tapping Record. Clips are capped at four seconds.
Direct practice keeps up to two completed recordings of the current word for
explicit listening. **Record another try** preserves the current recording;
a third try first removes the oldest, before requesting permission or allocating
another file. **Play earlier try** and **Play latest try** share one player and
switch only after its exact stop is acknowledged. A denied or failed replacement
can return to the retained recording without starting capture or playback.
**Delete both tries and start over**, advance, session exit, background and
interruption remove the owned takes. Stale temporary clips are removed at recorder startup. A deletion
failure blocks further recording until restart rather than claiming successful
cleanup. The direct flow constructs no enrollment model and calls no network API.

Direct practice also offers **Show mirror** below the audio controls in Debug and
Release builds. It is
an optional local front-camera preview with no frame analysis, camera recording,
image storage, upload or speech verdict. Permission is explicit; Cancel returns
to audio practice. Normal simulators report unavailable without requesting camera
access. Generated verification hosts show a clearly labelled sample image.

Hide, Close, inactivity, background and completion revoke the preview. Failed
camera shutdown retains its owner and offers **Retry turning off camera**. Close
pauses practice until both audio/file cleanup and camera release are confirmed;
an ordinary camera failure still permits audio practice. Recovery stays reachable
on the completed-practice screen. Neither returning to the screen nor starting
more practice automatically reopens the mirror. Camera-lab experiments and
generated verification hosts remain Debug-only. The October 12 verification passed
Debug and unsigned Release builds, all 44 selected unit checks and all 14 selected
Debug mirror interaction checks, with source/resource checks and confirmed cleanup.
Both built apps include the camera purpose description. Physical camera operation
and Release-runtime interaction remain unverified. See [native mirror verification](../../docs/consumer-assessment/native-mirror-verification-20261009.md)
for generated checks and physical-camera limits.

Completed practice saves up to 100 local metadata entries: session ID, completion
date, sound group and word count. The home screen shows the latest three and an
explicit Clear action. This records participation, not speech improvement. No
word, recording, age, identity or pronunciation score is stored in history.
Writes are atomic and request complete iOS file protection; the store's dedicated
directory is excluded from backup. Actual data protection needs physical-device
verification because the simulator does not expose its protection metadata.
Unreadable history is preserved until explicit clear. Save failures remain visible
without blocking more practice. Direct completion offers **Try saving again**
with the same frozen session ID, date, sound and word count; retry does not capture
audio, alter participation or duplicate the session. Close or starting fresh
practice abandons this in-memory retry. See [direct two-try and save-retry verification](../../docs/consumer-assessment/native-two-try-verification-20261011.md)
for the separate generated test groups, preserved failures and hardware limits.

Save outcomes now use completion-bound accessibility announcements. Initial save
failures and each accepted retry report their outcome, including repeated failures
with identical text. Close or starting fresh invalidates the old event; visible
messages and focus stay unchanged. The [history-save announcement check](../../docs/consumer-assessment/native-history-save-announcement-verification-20261020.md)
passed thirteen focused simulator tests. Actual VoiceOver speech delivery remains
unverified.

## Internal speech check — simulator Debug builds only

### Combined recording feedback

Start the [reviewed unified consumer service](../../research/assessment-consumer-unified-app/README.md)
on this Mac at `127.0.0.1:8793`, then open **Record with feedback** on Home, or launch
with `-CadenceFeedbackMode`. This Debug simulator screen uses the fixed 15-entry
word catalog. One session owns up to two temporary recordings for replay. Only its
current latest take can be word-checked or used for the separate adult-only bread
sound comparison. No second recorder or screen owns those files.

Record and replay work with who-is-practicing unset and checking off. Before recording,
choose **Adult (18+)** or **Child, age 6–12** and allow word checking if wanted. A word
request uses schema2 with that exact captured context; adults never receive an invented
child age. Then explicitly tap Check for the take. Sound comparison additionally needs
adult context, the canonical bread prompt and both adult-testing/sound options. Tap
Check sound separately. Either checking order retains both results on the same take;
only one check may run at a time. Each path claims a take once. Nothing captures or
uploads automatically, and setting a context does not verify age or participant consent.

Word results separate recording observations, speech detection and whole-word recognition.
Sound results are uncalibrated whole-recording BR/BW/BL/R-omission model preferences or
inconclusive observations. Neither establishes which phone was produced, pronunciation
correctness, child/adult accuracy, improvement, treatment or diagnosis. No results are
saved to participation history or imported into the older research assessment ledger.

Changing word/context/word-check consent clears the take and resets both sound boxes.
Sound option changes likewise require a fresh take. Retake, canceling a check, next, close, background and
interruption revoke operations before disposal. Late replies cannot restore old results.
Server cleanup uncertainty pauses both remote checks persistently while local recording
and replay remain possible. Failed local deletion separately blocks media. Cancelling a
word URLSession task does not confirm server cleanup; prepared sound cancellation/reset
uses exact ownership, and remote-control failure also pauses both checks. Both clients
verify fresh declarations and exact reviewed source/model/policy/content pins.

All these research clients/views/fixtures remain under Debug-and-simulator guards;
the entry is absent on physical devices and in Release. Simulator/generated verification
does not establish microphone performance, real-speaker accuracy or release eligibility.
See [native unified verification](../../docs/consumer-assessment/native-unified-practice-verification-20261007.md) for actual checks and limitations.

### Two tries for self-listening

After a valid recording, **Record another try** keeps it for listening while starting a
fresh take. **Play earlier try** and **Play latest try** share the existing player with
**Play example**. Switching playback never restores earlier check results or eligibility.
Only the newest valid current take can be checked; each Check remains explicit. No
better/worse verdict, score, automatic correction or improvement claim is added.

Recording a third try removes the oldest before requesting microphone permission or
allocating another recording. A deletion failure stops that action. Denied or failed
replacement can preserve the previous valid recording for replay only; checking needs
a fresh recording. **Retake/Clear both tries**, changing settings, canceling a check,
Next, Close, background and interruption clear the owned recordings. A newly failed
local cleanup on Close stays visible before a second Close can leave; a file may remain
when removal fails. Public-example cleanup failure stops new capture/example allocation
but preserves safe replay of existing private recordings after the shared player stops.

This is free practice only. Guided sessions keep their existing one-take workflow and
metadata-only completion history. Generated `twoTries`/`twoTryCleanup` fixture cases
are explicit simulator UI seams, not audio-output or model-accuracy verification.
See [two-try verification](../../docs/consumer-assessment/native-two-try-listening-verification-20261007.md).

### Continue from recent practice

Each of the three recent participation entries offers **Practice again** to open
that sound's existing word library. Choose a position or word for fresh practice;
the history does not retain the previous word, position, audio or assessment.
Opening the library and returning Home do not record or save another session.
Home passes its selected history store through the library, search and player,
so generated verification remains isolated. Unknown sound IDs are rejected by
the unchanged history schema rather than mapped to a different group.

### Finish recorded free practice

Free **Speech practice** offers explicit **Finish practice** after a valid recording
retained in the current word/settings visit. Two tries count as one practiced word.
A safe previous recording after a denied or failed replacement may qualify for
participation even though it cannot be checked. Opening, example listening, a check
result, Next and Close never save automatically.

Finishing clears both owned recordings and any public example before writing to the
same **Recent practice** store shown on Home. Cleanup failure prevents saving. The
existing metadata stays UUID/date/chosen sound group/wordCount1; no audio, word text,
age or check result is saved. The full 15 canonical prompt mappings include the distinct
middle-baby and end-backpack targets. A selected group is practice participation, not
a detected difficulty or improvement.

An unconfirmed write offers explicit **Retry saving** with the same UUID, date and
payload, including when a writer may already have persisted it; retry cannot duplicate
that visit. A missing writer reports that saving is unavailable. **Practice again**
starts a fresh visit without automatic recording/checking or clearing lifetime limits
and a shared service pause. Changing settings, Next, background/interruption or Close
abandons the in-memory retry; no automatic retry queue is added. Guided completion,
store schema/capacity/clear and check contracts remain unchanged.

All generated free fixture cases use an isolated real history store shared exactly
with Home. If guided/free flags coexist, both borrow the existing guided isolated
store first. Only an ordinary launch uses shared production history. Generated cases
`freeCompletion`, `freeSaveFailure`, `freeDeniedReplacement` and `freeCleanup` are
sensor/model/network-free seams; they do not establish actual capture, audibility,
pronunciation accuracy, clinical efficacy or diagnosis.

### Listening and manual comparison

Speech practice offers explicit **Play example** and **Replay this try** through the
same player. Listening works before setting a context or enabling either check, and
keeps the current take, both results and consumed check claims. A generic canonical
bread cue invites listening for b followed by r and manual comparison; it is not a
finding about the learner's pronunciation. Examples remain available while remote
checks are paused; failed example playback does not invalidate the learner recording.

The closed 15-prompt lookup uses 13 existing licensed public WAVs. Full canonical
prompts are required; yo-yo maps to the allowlisted `yoyo` route. Loading happens only
on tap through a public full-file GET on8793 (no Range or processing request), with
fixed registry SHA256, PCM/sample-count validation, a132096-byte streaming limit and
a10-second overall deadline. Speaker ages are unknown and examples are not clinically
approved. The source/license disclosure preserves attribution, conversion changes
and the reported source variety. No example audio is bundled in the app target.

Switching sources stops the existing player. Cancel, setup changes, record/check,
retake/next/close, background and interruption invalidate pending loads and callbacks.
One separately owned public example file is removed after use; a failed removal keeps
its exact ownership and blocks further example files until **Retry example cleanup**
succeeds. It never calls the microphone capturer's discard method merely to listen.
These additions retain the Debug-and-simulator boundary; no Release/device eligibility
or human hearing/accuracy is established by source or generated UI checks.

`ResearchPracticeExampleLoopbackTests` is an opt-in actual public-example GET plus
AVAudioPlayer completion check, enabled by `CADENCE_PUBLIC_EXAMPLE_LOOPBACK=1`. It
needs the `TEST_RUNNER_` prefix when passing that flag through `xcodebuild`.
never records, processes a learner clip, resets the service or accesses private data.
Its successful delegate/file cleanup would establish execution, not human audibility.
The unit-test bundle's `public-example-bread.wav` is an unchanged public licensed
fixture with its credit alongside it; generated loaders use distinct data and credits.
See [native listening verification](../../docs/consumer-assessment/native-listening-practice-verification-20261007.md)
for the separately recorded actual checks and remaining limitations.

`-CadenceUnifiedFeedbackUITestCase combined|cleanup|listening|loadingExample|unavailableExample|cleanupExample`, together with `-CadenceFeedbackMode`,
selects only visibly labelled generated native fixtures. They start canonical bread with
all contexts/consents unset; Record/Stop/Check remain explicit. Generated owned PCM and
invented contract-validated replies and a separately labelled generated example exercise the actual session/view, with no microphone,
camera, network or speech model. Ordinary launches have no fixture. Independent Python
schema2 adult/child vectors compare the actual native client's bytes through controlled
URLProtocol; those tests do not perform live HTTP inference.

`ResearchFeedbackLoopbackTests` remains an optional generated-silence POST test. Do not run
it against an owner-used8793 service/runtime during agent verification. Current delivery
verification uses controlled POST fixtures and a selected public-declaration-only GET;
no recording or private owner runtime is inspected.

### Standalone adult sound preview

**About → Sound preview** or `-CadenceSoundMode` retains its independent take owner for
standalone investigation. It now pins the same unified8793 service as word feedback;
its file is never shared between separate sessions. Both adult confirmation and sound
processing start off. Recording/replay work alone; turn on both options before a new
bread take and explicitly choose Check sound. A declaration is not verified age or consent.
Shared server-cleanup pause and local-file cleanup remain distinct. Nothing enters history.
The entry/client remains absent on physical devices and in Release.

`-CadenceSoundUITestCase br|bw|other|inconclusive|paused|cleanup|cancelled` retains the
separate explicitly labelled, generated, sensor-free standalone UI fixtures. Their
historical source metadata is preserved unchanged; current-source positives use distinct
new unified vectors. Existing original8788 and sound-practice8789 services and previously
built binaries retain their exact historical bindings, which current native clients reject.

Current feature SHA256 is `af0ebd33f9a17ab6860e50314433e50691db7299d100874991885945cccb9057`.
`ResearchSoundSuccessorLoopbackTests`, selected with
`TEST_RUNNER_CADENCE_SOUND_UNIFIED_DECLARATION_LOOPBACK=1`, performs only one exact8793
public declaration GET. It sends no observation/cancel/reset POST, reads no recording or
private runtime, and invokes no model. Historical verification receipts are not rewritten
as evidence for this version.

### Earlier internal research check

Start the [local research service](../../research/audio-head/consumer_assessment/README.md)
on this Mac, then open About → Speech check lab, or launch with
`-CadenceAssessmentMode`. It requires reading the explanation, choosing a completed
age 6–12 and a word, and switching local processing on before Record. The 15-entry
engineering pack is awaiting qualified content review. The /ZH/ example explicitly
exercises unavailable scope. The client uses only `127.0.0.1:8765`, refuses redirects
and validates version, audio/request/prompt/target/model bindings and all disabled
eligibility flags. A physical phone cannot reach the Mac through this endpoint;
the entry is absent there and in Release builds.

The existing actual microphone recorder creates mono16kHz PCM16 WAV, at most four
seconds. Too-short or quiet captures are cleaned without sending. Accepted captures
are sent to the local service; its predictions remain internal and prompt matching
is unverified, so the app shows an honest unavailable explanation and offers retry
or ordinary practice. Native audio is removed on processing outcome, cancellation,
interruption, background and close. Late callbacks cannot revive a discarded
attempt. Cleanup failure disables further capture until restart. The service removes
its temporary files after bounded processing; client cancellation can leave that
work running until completion or timeout. Abrupt host death cannot guarantee cleanup.

The session's Debug-only attempt ledger stays in memory. Record starts accounting
before permission; explicit unsupported preflight rejection is also counted without
audio. Each started attempt receives one terminal outcome, including cancellation,
cleanup failure and processed-but-unverified output. Retry IDs link only unchanged
setup; the same caller-owned ID binds the HTTP request. The latest 100 rows retain
monotonic elapsed durations and fixed reasons, while session-lifetime totals retain
dropped rows. No prompt, age, child identity, audio or probabilities enter this ledger.
Closing the lab discards it; it is separate from persisted practice participation.

The [assessment specification](../../docs/consumer-assessment/assessment-v1.md),
[catalog audit](../../docs/consumer-assessment/catalog-coverage.md) and
[confirmatory preparation draft](../../docs/consumer-assessment/r-confirmatory-preparation.md)
record separate research/product gates. This lab does not establish child accuracy,
pronunciation correctness, treatment suitability or physical microphone performance.

Synthetic simulator verification also checks Apple's actual PCM16 WAV bytes and
the app's file reader without capture. Optional `ResearchAssessmentLoopbackTests`
use the running local service: silence remains unavailable and a deliberately
nonspeech Apple-generated WAV exercises the real processed-but-unverified model
path. Both passed without skips with the service present. Processing that tone
does not establish speech or prompt matching. No sensor permission, recording or
playback occurs in these checks. The physical protection method explicitly skips
on the simulator; the owner requested simulator checks only. See the
[runtime checkpoint](../../docs/implementation/consumer-assessment-runtime-20261002.md).

Generate the project with `pnpm ios:generate`, open `CadenceLearner.xcodeproj`,
choose an installed iPhone simulator, and run the `CadenceLearner` scheme. No
signing team is needed for a simulator build. Tests use the same scheme; select a
specific simulator ID when multiple runtimes contain the same device name.

In Xcode 27, open **Xcode → Open Developer Tool → Device Hub** and select the
running iPhone to see its screen. See the
[delivery record](../../docs/implementation/native-demo-checkpoint.md) for
verification evidence and the separate baseline failures in the old clinical UI.

The About sheet contains a **Camera lab** entry in Debug builds on supported
physical devices. It runs real ARKit face tracking and displays four expression
measurements after explicit camera opt-in. It saves no images, audio, or readings.
It has no pronunciation-scoring role. The entry is absent in the simulator;
physical sensor behavior still needs phone testing. See the
[camera note](../../docs/model/truedepth-feasibility.md).

## Existing linked-device foundation

The Gate 1 learner flow remains available in Debug with the launch argument
`-CadenceClinicalMode`. Existing `-accessibility-*` audit launch arguments retain
their previous behavior. These paths provide the existing
SwiftUI prompt/record/quality/retry flow with camera-off behavior and consume
the generated `CadenceContracts` Swift package. A caregiver can enroll the
device with a short-lived clinician-issued token. The token is saved only after
the server authenticates it, and every launch refreshes the clinician's current
consent-bound assignment. The app records mono 16 kHz PCM WAVE, uploads only
after a clear local capture with exact assignment/repetition/retry evidence,
accepts a silent-practice receipt, advances the bounded dose, and deletes the
temporary file on retry, success, or failure. It must
not be used with patient data because providers and clinical gates are not
approved.

The server gives each valid enrolled device separate hourly budgets for
assignment refreshes and attempt uploads. A `429` response carries
`Retry-After`; the native client preserves that delay and presents calm retry
guidance without discarding enrollment. This is not a substitute for the
provider-edge invalid-token/IP controls still required before deployment.

Generate and test the project:

```sh
xcodegen --spec apps/ios-learner/project.yml
xcodebuild \
  -project apps/ios-learner/CadenceLearner.xcodeproj \
  -scheme CadenceLearner \
  -destination 'platform=iOS Simulator,name=iPhone 17 Pro' \
  test
```

The microphone is activated only after the learner presses the record button.
Enrollment and navigation never require speech. Credentials are stored in the
iOS Keychain with this-device-only accessibility.
No shipped target protocol is visual-feedback eligible, so production builds
do not request camera permission. The Gate 2 feasibility foundation includes a
local Apple Vision face/lip landmark extractor and derived framing coach. It
never saves camera frames or uploads visual evidence. In a Debug build on a
physical device, pass `-CadenceVisualFeasibility` as a launch argument to enable
the non-patient-data camera-quality option. The tester must still choose the
camera action after reading its local-processing explanation. This mode cannot
enable visual consent or model-generated articulation feedback.

Select one report scenario per launch with:

```text
-CadenceVisualFeasibility
-CadenceVisualScenario
protocol-compliant
```

After frames are processed, the Debug UI can export an aggregate JSON report.
It contains no frames or raw landmarks. Validate a complete private report set
with `pnpm --filter @speech-therapy/visual-evaluation evaluate <files...>` and
follow [`docs/validation/visual-feasibility-protocol.md`](../../docs/validation/visual-feasibility-protocol.md).

See [`docs/model/visual-landmark-runtime.md`](../../docs/model/visual-landmark-runtime.md)
for the MediaPipe comparison, privacy constraint, evidence boundary, and
replacement gate.

## Optional independent speech admission — simulator Debug builds only

About → **Speech admission lab** uses the separate [local admission service](../../research/assessment-mobile-admission/README.md) on `127.0.0.1:8778`; the existing **Speech check lab** keeps the original8765service. Launch with `-CadenceAssessmentMode -CadenceAdmissionMode` for the new route. Reading the optional-processing explanation, age/word selection, local-processing opt-in and a separate Record action are still required. Ordinary practice remains immediate and works without an account or service.

The new path independently checks speech and requested-word admission before invoking the frozen research model. Admitted processing produces no pronunciation finding and cannot indicate whether the word was said correctly or incorrectly. Recognition rejection does not establish a pronunciation problem. No transcript, model probability, score or diagnostic result reaches the public response or in-memory native ledger. Exact byte/prompt/request/attempt/source/model/policy bindings and every disabled claim flag are checked; the underlying bridge's prompt match remains unverified. The new transport is compiled only for Debug simulators and refuses redirects.

The server writes a cleanup intent before starting trusted nested workers and blocks further processing when cleanup cannot be confirmed; a blocked runtime requires deliberate owner recovery. Client cancellation deletes native temporary audio and ignores late responses, while service work may continue until bounded completion/timeout. Abrupt service or host termination can leave private temporary files; removal is not guaranteed. Sensor-free Apple-generated WAV and a licensed public fixture exercise the new endpoint in focused simulator integration checks. Simulator evidence cannot establish physical capture/protection, intended-child accuracy or clinical/production eligibility. The [new verification receipt](../../work/roadmap-completion-20261004/mobile/verification.json) distinguishes actual checks from unit seams and preserves exact historical mobile copies before source supersession.

## Guided word check — simulator Debug builds only

Home → **Guided word check** (or `-CadenceGuidedWordMode`) adds a self-declared child6–12 flow using the existing unified8793 whole-word client. Choose an age and explicitly allow checks, then record/check each of13 words. Recording, checking, navigation, example listening and recheck are separate user actions. This is recognition observation, not target-sound assessment, pronunciation correctness, diagnosis or demonstrated improvement. Child sound comparison is inaccessible in guided mode.

The roster preserves all15 canonical prompt bindings while deduplicating baby/backpack to13 word items. The first submitted check fixes each round's primary outcome; pre-check retakes and unsubmitted failures remain separate attempts. Every summary keeps13 dispositions, including skipped and not reached. Recording attempts, submitted checks, client requests started and validated responses are separate counts. A request start establishes neither complete upload nor server receipt/inference. Practice leaves first-round observations unchanged. Recheck requires fresh capture/take/attempt identities for the same age, roster and pinned source/policy; identical audio hashes remain a comparison limitation. Only pairs with two lexical observations are paired, with no score or improvement percentage.

One `ResearchFeedbackSession` owns media across all stages. Pending permission, private deletion failure, public example cleanup and common processing pause retain their guards. Licensed examples use the same bounded/pinned loader and player as free practice. Age, results and guided attempts stay in memory, with temporary clips removed on transitions/leave as ownership allows; unresolved cleanup remains visible. `-CadenceGuidedWordUITestCase mixed|denied|delayed|paused|cleanupExample|cleanupRecording` supplies explicitly generated PCM, invented contract-bound replies and simulated request starts with no network, microphone or model. Generated playing states cannot establish actual audio output: the separately retained native public-example playback check failed after valid bytes/hash/PCM, so native audibility remains open.

The dated [guided verification guide](../../docs/consumer-assessment/native-guided-word-flow-verification-20261007.md) records actual executed checks and limits. Release compilation excludes this experimental flow; no Release execution or physical-device validity is implied.

Guided manual practice now offers **Finish practice** only after at least one valid new recording in that visit. Finishing attempts owned-media cleanup first, then saves one word to the existing **Recent practice** store. Opening/listening, a recognizer result or leaving without finishing saves no participation. Saved metadata stays at schema1: UUID, date, the chosen existing sound group and wordCount1; no age, prompt text, audio or assessment results. The group describes selected practice, not a detected difficulty. Capture measurements and participation do not establish correct speech or improvement. Failed writes show **Practice not saved** with a same-visit **Retry saving**; there is no automatic save on leaving/background, and retries cannot duplicate that visit. Existing history capacity/clear and file protection are unchanged. Generated guided fixtures use isolated real stores; `historySaveFailure` fails the first save before writing. [Practice-history verification](../../docs/consumer-assessment/native-guided-practice-history-verification-20261007.md) will distinguish actual checks and remaining boundaries.

### Choose a short practice plan

The first-round summary offers **Choose words to practice**. Choose one to three
of the same 13 words; none is preselected. Optional suggestions require an original,
validated primary **model not matched** observation. Quiet/clipped recordings,
uncertain checks, unavailable checks, skipped words and unreached words are
explained separately and do not supply suggestions. A matched word remains selectable.
These are whole-word observations, not detected sound errors or a treatment prescription.

Confirming starts an ordered sequence with a fresh practice visit for each word.
Record, replay, optional example listening, **Finish practice**, **Skip**, and
**Next word** remain separate actions. Plan recordings are local manual practice;
they cannot be submitted for a check. Finishing reuses the existing cleanup-first
participation writer and never advances automatically. A failed save keeps its
frozen completion ID for **Retry saving**, or an explicit **Continue without saving
again** action. The report distinguishes explicit finishes, unconfirmed saves,
skips, visits left unfinished and words not started. It does not resave visits.

**Edit plan** retains the report while choices are edited; confirming replaces that
in-memory report with a new sequence and fresh visits. **Start recheck** always
starts the full fresh 13-word round. The plan does not replace first-round results,
alter counts, reset a processing pause, or add history fields. Pending permission
and unresolved media cleanup retain the existing navigation guards. This feature
remains Debug/simulator only. The [practice-plan verification guide](../../docs/consumer-assessment/native-guided-practice-plan-verification-20261007.md)
records executed checks and their limits.

## Native home speech entry (Debug simulator only)

Home now opens **Guided word check** and **Record with feedback** directly. Each
presentation constructs the existing destination with a fresh media owner; Close
returns Home rather than an About navigation stack. Opening never chooses an age,
opts in, records, loads examples, checks, or saves practice. One research route is
presented at a time; conflicting legacy mode flags prefer guided, feedback, sound,
then assessment. The old labs remain in About. Local Start practice and sound search
remain available. Recent practice appears before the sound library, with the same
three-entry display, store, schema, capacity and explicit Clear behavior.

Privacy text distinguishes device-local ordinary practice from explicitly requested
checks sent to the existing service on this computer, and example recordings fetched
only on Play. Generated guided/unified fixture flags show a Home banner and retain
their existing isolated seams; normal Home navigation needs no destination mode flag.
The [home-entry verification guide](../../docs/consumer-assessment/native-home-speech-entry-verification-20261007.md)
records actual checks when executed. Research entries remain excluded from Release
and physical-device builds; easier navigation does not validate diagnosis or audibility.


## On-device review, practice and recheck

Debug simulators additionally offer **Run the local research sound model** in
this flow's setup. Start the existing same-Mac service on port8765 and declare
the child's known age6–12 before Start. After an explicit Check and a native
whole-word match, the exact recording reaches the complete research feature/head
pipeline. Practice and fresh recheck keep separately bound processing notes;
no pronunciation verdict, score, correction or automatic practice selection is
enabled. Unknown server cleanup pauses model requests across sessions. See the
[implementation and actual verification report](../../docs/consumer-assessment/native-guided-model-integration-20261014.md)
for startup instructions, preserved word-admission failures and the distinction
between real inference, generated checks and microphone validation.

The Debug client now retains each validated target distribution with the exact
request, audio and prompt hashes, declared age and model manifest. Guided processing
keeps this result only in session memory beside its original operation and take;
wrong bindings, cancelled results and unavailable processing retain no score payload.
The word-only review ledger, saved practice and learner notes do not interpret or
persist those research distributions as pronunciation correctness. Timing-only
processor stubs do not count as a validated guided research result.

Home → **Review, practice, recheck** opens a local five-word flow in every build.
Choose five different words from the existing library; the starting set is ball,
pig, moon, tiger and dog. Start freezes their canonical sound, position and order.
Record, Stop, Play and Check remain explicit actions. The first admitted check is
kept for each review visit. Results describe whole-word recognition only; they do
not assess individual sounds, pronunciation correctness or diagnosis.

Setup offers **Save these five words**. This explicitly saves one ordered set of
canonical library choices on this device, without recordings, results, age or
assessment history. Saving a different set replaces the previous set. Home's
**Saved words → Open saved words** opens editable setup; it does not start a
round, recording or check. **Clear saved words** requires confirmation. An
unreadable or unsupported saved file stays untouched until explicit clearing;
failed saves remain visible and do not prevent starting the current setup.
The store uses a bounded, versioned file in its own protected, backup-excluded
Application Support directory. Generated routes inject their own store or omit
the feature, so they do not use the ordinary saved set.

Saved-word persistence and the native results list were checked on the dedicated
SE (third generation), iOS 26.5 simulator: 15 unit checks and six generated UI
checks passed, including the actual largest accessibility text size, relaunch,
replacement, confirmed clearing, filesystem failures, row pans and keyboard/search
state. The current ordinary Release was built and installed; all 26 installed
bundle files matched the build. A setup-only ordinary-app check covered empty
results, disabled duplicate words and Cancel preserving the five choices. These
checks used separate test stores and no microphone, camera or recognition; they
do not establish sound-specific accuracy or clinical validation.

Choose one to three of the original words to practice; none is preselected. A
practice visit requires a fresh valid recording and explicit completion. Only
completed practice writes the existing participation metadata, with the exact
visit UUID retained for save retries. Review and recheck write no history. On the
last word, the main button names
the next step: **Choose practice words**, **Finish practice** or **View summary**.
An unconfirmed practice save keeps **Continue without saving** and its save retry.
Start recheck revisits all five original words with fresh visit/take identities. Partial
summaries distinguish skipped from not reached and preserve the first results;
paired observations make no improvement claim.

Selected practice shows **Try this** before Record, using the existing guide for
the exact word, sound and position. Unsupported canonical targets receive only
whole-word record/replay guidance. Each fresh selected-practice visit opens at its
word; the instruction may require scrolling at larger text sizes. Initial review,
recheck and ordinary practice keep their existing presentation.
Expanding About omits the duplicate short instruction while retaining the full
explanation and Sources. This is general guidance, not a detected sound error.
See the [instruction verification](../../docs/consumer-assessment/native-practice-instruction-verification-20261024.md)
for the retained first attempt, positioning correction, checks and limits.

The final summary also shows **Practice** for each original word. It distinguishes
unselected words from selected visits that were skipped, not reached, completed
with saved participation, or completed with an unconfirmed save. The join uses
canonical entry IDs and preserves the frozen first-review and recheck observations;
practice participation is not a measure of sound improvement.

In a Debug simulator with guided research processing enabled, **Research details**
on practice selection and the final summary opens retained first-review and recheck
distributions for that exact entry and take. Missing results are explicit. These
are internal, unvalidated corpus-rating probabilities, not learner feedback or
diagnosis. Opening the sheet performs no new processing or history write. This
view and its controls are excluded from Release and physical-device builds.
The guided research wrapper now receives the exact stopped recording from the
media session, including its capture measurements and registered producer owner.
Research callers must prepare the exact canonical entry/visit and use the atomic
captured-context capability; a URL-only word check cannot authorize research
processing. Unconfirmed or sibling word receipts retain the wrapper's independent
file protection. See the [owned recording handoff verification](../../docs/consumer-assessment/native-owned-capture-handoff-verification-20261024.md):
56 focused unit checks and two generated normal/largest-text UI journeys passed.
No hidden model was connected and no pronunciation finding was enabled.

The [October 24 verification report](../../docs/consumer-assessment/native-guided-feedback-review-20261024.md)
records 76 unit passes, two generated compact/largest-text UI passes, the ordinary
Release build and skip-only UI pass, preserved failures, and the unresolved Release
view-hierarchy warning. These checks do not establish real speech accuracy.

The continuation labels passed three coordinator checks and compact/native-largest
UI journeys on the dedicated SE/iOS 26.5 simulator. These cover actual destinations,
one/three practice visits and history-save failure/retry. The current ordinary
Release was built, installed and matched across all 26 bundle files; a Home-to-setup
check left its data unchanged. Generated capture/check doubles establish control
behavior, not speech accuracy or physical capture.

During practice, **Next word** requires the latest take to pass the existing
recording-quality checks with finite measurements. A rejected latest take keeps
Next disabled even when an earlier take was acceptable; Record another try,
Skip and Close remain available. A word-check match is not required to complete
practice. See the [quality-eligibility verification](../../docs/consumer-assessment/native-guided-practice-verification-20261012.md#practice-next-quality-eligibility-october-15).

The word picker keeps Cancel in a sticky header, with its hit shape inside the
button label. Search stays above the results and uses a single-line native field;
Return dismisses the keyboard. A changed ordered result set starts at the top,
while an unchanged result set retains its scroll position. Clearing search restores
the library under the current sound and position filters. Sound keeps its native
menu. Position expands in place to **All positions**, **Beginning**, **Middle** and
**End**, marks the current choice, and collapses after an explicit selection.
Opening the choices dismisses search focus without clearing the query. Clear
search has an explicit 44-point rectangular target.
The [October 24 Position-filter verification](../../docs/consumer-assessment/native-guided-position-filter-verification-20261024.md)
records compact/largest-text Release passes and a preserved full guided-round
regression, with original failures and exact build provenance. The old Position
menu's hierarchy warning did not recur in these runs; this does not qualify other
menus or actual media behavior. The [earlier ordinary Release UI verification](../../docs/consumer-assessment/native-release-navigation-verification-20261015.md)
passed a compact skip-only journey with position selection/reset and a requested
Accessibility XXXL setup/Cancel/first-visit/Close journey. Both app and UI-test
module were optimized with testability disabled. The new suite is Release-only;
these checks do not exercise media or speech recognition.

Completed summaries offer **Review these five again**: the same ordered five
entries start a fresh first-review round within the same open workflow/media
owner. Previous observations and selected practice are cleared; recording,
playback and checks remain explicit, and existing history is unchanged. Done
still closes. Failed preparation preserves the summary and existing recovery.
The picker now keeps its unchanged search row below sticky Cancel, outside the
scrolling filters/results, preserving Dynamic Type and Return handling. Two
largest-text focused probes and both original compact/largest-text repeat
journeys pass on that layout, with the original full-flow allowance unchanged. See the
[repeat verification](../../docs/consumer-assessment/native-guided-repeat-verification-20261016.md).
These four current Release UI checks use no media or recognition; earlier
coordinator unit results remain separately bound historical evidence.

Recent practice previews three entries and offers **View all practice (N)** for
the complete retained history. The destination observes the same bounded store,
keeps native Back and shows distinct empty/unreadable states. **Practice again**
opens that sound's word library. Six generated UI cases pass, including the
100-entry largest-text case, cancelled/confirmed Clear, failed-Clear retry and
an observed Clear without an unexpected pop. The ordinary Release compact smoke
also passes. See [history-access verification](../../docs/consumer-assessment/native-history-access-verification-20261016.md)
for historical unit reuse and preserved failures. The later [Clear confirmation repair](../../docs/consumer-assessment/native-clear-confirmation-verification-20261016.md)
passes all eight history UI cases and an ordinary Release smoke; direct screenshot
review confirms complete compact/largest-text explanation and persistent actions.
VoiceOver/keyboard inspection remains open. No recordings or speech results enter history.

Search and sound-library practice sheets refresh Home's existing cleanup snapshot
on dismissal, without automatically retrying deletion. Opening a card no longer
forwards the mirror stream's initial snapshot as a parent change during rendering;
subsequent mirror transitions still forward synchronously. Eight unit cases and
two ordinary Release routes pass with no runtime warnings. See [nested-practice
verification](../../docs/consumer-assessment/native-nested-practice-verification-20261016.md)
for the preserved rejected run and scope: failed-file dismissal, passive counters
and live media were not exercised by those UI cases.

Each retained take can show **No sound was saved in this try** or **Recording
reached its volume limit** from its own exact PCM16 evidence. Unsupported
evidence adds no badge; existing quality gates and practice completion remain
unchanged. Earlier/latest labels, replacement and cleanup keep advice bound to
the exact take. The [recording-feedback verification](../../docs/consumer-assessment/native-recording-feedback-verification-20261016.md)
covers 32 unit cases with actual generated WAV reads, two optimized Release
component journeys and a separate ordinary Release smoke. Twelve inspected
screenshots cover complete advice copy at compact and largest text sizes.
Generated capture and silent playback dependencies do not prove live media.

Completed word-check outcomes now stay beside the recording they checked. **Earlier
try** and **Latest try** each keep their own whole-word match, no-match or unclear
result. A new unchecked take says it has no result, and a third take removes the
oldest recording and its observation together. These statuses are temporary; no
transcript or new history field is saved. Processing failures and current-only
word guesses remain separate, and guided first-review observations stay frozen.
See the [retained word-check verification](../../docs/consumer-assessment/native-retained-word-check-verification-20261024.md):
45 focused unit checks and four generated simulator journeys passed, including
normal/largest-text comparison and guided practice through fresh recheck. These
checks establish identity and behavior, not pronunciation accuracy.
An unmatched or unclear latest check in selected practice also explains that a
word match is not required, when both moving on and recording another try are
available. The cue belongs only to the latest result and preserves existing
recording-quality and cleanup requirements. See the [decision-cue verification](../../docs/consumer-assessment/native-practice-decision-verification-20261025.md).

After an eligible word-only check times out and confirms cleanup, **Try word check
again** reuses the latest recording with a new check operation. With two takes,
the label explicitly names the latest try. Retry requires a tap; it never starts
new capture or duplicates practice credit. First-review and recheck submissions
remain frozen. The Debug guided research composition is excluded, including when
opted out. See the [timeout-retry verification](../../docs/consumer-assessment/native-timeout-retry-verification-20261024.md):
43 focused unit methods and six generated Debug UI journeys passed, with a
separate successful ordinary Release build. These checks do not establish real
timeout frequency, Release runtime behavior or sound accuracy.

Starting a recording or retake now brings **Stop recording** fully into view
when ready/review content collapses above it. The [recording-transition verification](../../docs/consumer-assessment/native-recording-transition-verification-20261025.md)
covers eight generated first/retake observations across ordinary and selected
practice at normal/largest text, plus two ordinary Release navigation journeys
on the current source. Release navigation does not exercise recording or timeout
retry; real media, sound accuracy and VoiceOver remain separate qualifications.

Selected-practice review now offers a collapsed **Practice reminder** above the
retake action. It reuses the current canonical instruction, closes for a new take
or practice visit, and starts no media or check. About keeps its other content
and Sources; its duplicate main detail returns when the reminder is collapsed.
See the [practice-reminder verification](../../docs/consumer-assessment/native-practice-reminder-verification-20261025.md):
seven instruction checks, two generated normal/largest-text journeys and two
ordinary Release navigation journeys passed. Reminder interaction after recording
is covered by generated capture, not ordinary Release media or sound assessment.
The reminder now precedes changing word-check and replay feedback, so a result
can arrive without pushing an open instruction out of reading position.
The [feedback-continuity verification](../../docs/consumer-assessment/native-reminder-feedback-continuity-verification-20261025.md)
records the original displacement and the corrected normal/largest-text generated
checks. It does not qualify ordinary Release media or individual sound accuracy.

When the view observes a new recording finish, its accessibility announcement now
includes that review's existing all-zero or volume-limit advice. Returning to a
kept recording announces readiness without repeating that advice. An active,
cancelling or blocked word check retains its own announcement. Nine pure XCTest
methods and the ordinary Release build pass; actual VoiceOver delivery and timing
remain unverified. See the [October 24 continuation](../../docs/consumer-assessment/native-recording-feedback-verification-20261016.md#october-24-accessibility-announcement-continuation).

One media owner remains alive across setup, recording, summaries and recheck.
Departure and Close require exact recording, playback, recognition and mirror
cleanup acknowledgments. Failed cleanup remains visible; an explicit retry can
rejoin the same departed visit/action without creating a replacement owner or
crediting the same practice twice. Background and interruption discard the
current recording as ownership permits and never resume capture or checks.

Native checks use the bundled English Whisper model through Core ML. The production
factory derives its resource location from the learner app bundle and requires the
fixed reviewed manifest. Resource hashes are verified when Check starts; constructing
a practice session does not load a model or run recognition. The worker admits the
whole stopped mono 16 kHz PCM16 recording, from 0.1 to 4 seconds, without cropping,
resampling or an expected-word hint. Only completed independent recognition is
compared with the requested word. The 15-second cooperative deadline requests a
stop; it does not promise that synchronous model work has already returned.
Cancellation and departure wait for the actual worker and timer before releasing
the recording borrow. Unknown cleanup keeps its owner and file retained. No audio
or recognized text is stored in the review ledger or participation history.
Existing Debug simulator service-based Word checks remain separate.

The dedicated simulator's explicitly authorized English asset installation passed.
Subsequent checks found installed and reserved assets but no compatible module
formats; both natural-format and no-preference negotiations returned nil without
running audio analysis. The preserved public bread reference case failed before
conversion/analysis, with exact cleanup and removal confirmed. A proven
pre-analysis format-unavailable result is presented as an unavailable check;
other uncertain results and cancellation keep their existing behavior. This
classification change did not make the Apple backend recognize speech. A separate
no-audio prepareToAnalyze(nil) observation threw typed noModel; its precise cause
remains unknown and was not retried. Sound-level preprocessing feasibility also
failed its fixed generated-only parity check before tracing or conversion; that
model is not connected to learner feedback. The Apple
backend and its failed observations remain preserved separately. The bundled Core ML
provider subsequently matched one licensed public engineering example on the
dedicated simulator with confirmed cleanup and temporary-copy deletion. That single
case does not establish broad accuracy, pronunciation correctness, child validity
or physical-phone performance. The integrated learner app subsequently passed
239 selected regression tests, Debug and unsigned Release simulator builds, and
one separate licensed-word case through its default factory, with exact worker,
timer and temporary-file cleanup confirmed. The recognition case ran in the
controlled Debug test host; at that checkpoint Release recognition and physical
capture remained unverified. A subsequent [Release runtime check](../../docs/consumer-assessment/native-release-word-verification-20261015.md)
matched the same licensed public word through the production default factory,
with worker/timer return and temporary-copy deletion confirmed. Its testable
Release simulator build passed ten selected checks after nine Debug regression
checks. This does not verify physical capture or the complete Release media flow.
A [later Release coordinator journey](../../docs/consumer-assessment/native-release-word-verification-20261015.md#release-guided-coordinator-continuation)
passed eight generated lifecycle checks followed by one real bundled-recognizer
journey: five initial checks, two manual practice takes with participation saves,
and five fresh rechecks. All twelve file-backed takes passed default quality and
confirmed deletion. The same public bread source supplied two matches and eight
deliberate prompt mismatches; hardware, permission and playback were doubled.
This verifies the coordinator/native-word path, not live media or accuracy.
The same integrated baseline also passed all12 selected guided-screen checks.
The separate fixed17 native coverage run matched12 of13 canonical words (sky
was not matched), rejected both deliberate mismatches, and produced no matches
on two generated nonspeech controls (silence uncertain, tone not matched). All17
confirmed owned-file cleanup; worker/timer joins were established for16 comparison
paths and remain unestablished for uncertain silence. These are simulator engineering
observations, not sound correctness, child accuracy or physical-phone performance.
The later mirror revision passed its separate Debug/unsigned Release builds,
44 selected unit checks and 14 Debug interaction checks with owned-process cleanup
and final simulator shutdown. No new speech inference was selected in that run.
The preprocessing-only diagnostic confirmed matching masks but a maximum
normalization difference of 1.52587890625e-05, exceeding the fixed 1e-6 limit;
its mean difference passed the separate 1e-7 limit. A valid-prefix correction is
being prepared separately; phonetic feedback remains unavailable.
Dated source and test evidence is kept in
`work/r-inference-checkpoint-20261012/native-guided-word-flow-v1/`,
`native-english-assets-v1/`, `native-word-capability-probe-v1/` and
`native-word-availability-feedback-v1/`; generated fixtures cannot establish real
speech, physical recording or clinical validity.

The integrated native recognition verification and independent review are recorded
in [the actual whole-app result review](../../work/r-inference-checkpoint-20261012/restart-native-ai-v1/ASTRA-NATIVE-GUIDED-COREML-ACTUAL-v1.md).

The current mirror result is recorded in [the October 12 independent review](../../work/r-inference-checkpoint-20261012/restart-native-ai-v1/ASTRA-NATIVE-RELEASE-MIRROR-ACTUAL-v2.md).
