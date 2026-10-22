# Native bundled word recognition and guided practice

The learner app now uses the bundled Core ML word recognizer for direct and
guided practice. A stopped recording is checked locally; the expected word is
compared only after independent recognition completes. Initializing the provider
does not open a recording, load a model or install speech assets. Recording and
recognition are explicit user actions.

The route uses the existing cached Whisper base.en weights, converted and
compiled for iOS 17 or later. The main learner bundle contains the pinned
`WhisperResources` folder. Resource validation binds the app identity, manifest,
model and tokenizer bytes. There is no alternate resource location or automatic
network backend. The production input gate accepts the complete stopped mono
16 kHz PCM16 take, between 0.1 and 4 seconds. It does not crop, resample, add the
expected word to decoding or warm the model before a check.

The 15-second policy requests a cooperative stop. It is not a hard wall-clock
limit: the real worker and deadline task must return before the exact recording
borrow can be released. A failed close retains the operation and its ownership;
it cannot grant completion credit or authorize deleting/replacing the recording.

## Actual integrated-app checks

The tested source inventory contains 338 pinned rows, 200 Swift files and seven
exact trees. The private build copy contains 230 source/resource files. Live
signing and account settings were unchanged. A current source-registration review
confirmed all93 app,87 unit-test and18 UI-test Swift files are present in the
correct build phases, with no missing, stale or duplicate entries. No project
regeneration is required. These checks used a separately generated private project preserving the source build configuration
and scheme, with explicit unsigned-build and Debug-dylib verification overrides.

| Actual check | Observed result | Scope |
| --- | --- | --- |
| Complete learner build | Debug and unsigned Release succeeded | Release runtime recognition has not been tested |
| Selected unit suite | Exact 239 tests passed, with no failures or skips | Source-bound software behavior |
| Real learner default factory | One licensed complete bread recording returned matched; all nine admission/ownership/cleanup booleans were true | One engineering example; whole-case elapsed time was 3,144 ms |
| Direct practice UI | Exact two tests passed | Generated current-take observation and retake/Close flows |
| Guided UI, compact text | Exact five tests passed | First check, skip, chosen practice, recheck, participation and cleanup flows |
| Guided UI, largest text | Five distinct tests for the corresponding journeys passed | Generated accessibility-size interaction checks |

Both actual controllers collected their exact twelve child stages and separate
outer parent, with exit zero, no signals, no remaining owned process groups,
unchanged source/build inventories and the dedicated simulator back in Shutdown.
The whole-app result and the generated UI result each received a separate clear
read-only Astra review. Generated UI cases add no real-speech successes.

Authoritative local evidence:

- [Whole-app actual checkpoint](../../work/r-inference-checkpoint-20261012/restart-native-ai-v1/CHECKPOINT-native-guided-coreml-actual-v1.json)
- [Whole-app actual independent review](../../work/r-inference-checkpoint-20261012/restart-native-ai-v1/ASTRA-NATIVE-GUIDED-COREML-ACTUAL-v1.md)
- [Guided UI actual checkpoint](../../work/r-inference-checkpoint-20261012/restart-native-ai-v1/CHECKPOINT-native-guided-coreml-ui-actual-v1.json)
- [Guided UI actual independent review](../../work/r-inference-checkpoint-20261012/restart-native-ai-v1/ASTRA-NATIVE-GUIDED-COREML-UI-ACTUAL-v1.md)

## Guided behavior and remaining work

A first round uses five unique words and preserves the first admitted
observations. Skipped and unreached words remain distinct. The learner explicitly
chooses one to three words, with none preselected, practices, and finishes that
practice before a fresh check of the same five words. Participation saves one
immutable visit record; retrying a failed save does not count another visit.
Paired observations are shown without claiming improvement. Recording and media
cleanup must be acknowledged before departure.

The fixed 17-case native engineering check completed with all cases observed:
12 of 13 licensed canonical examples matched; sky returned notMatched. Both
deliberately mismatched requests returned notMatched. Generated silence returned
uncertain and generated tone returned notMatched, with no control matches.
Every case confirmed whole-take integrity, an exact provider receipt, cleanup,
owned-file deletion and empty ownership. Sixteen comparison receipts establish
worker/deadline-task return; silence’s conservative join field remains
unestablished, without an inferred cause.

The exact selected XCTest and all eight native child stages plus the separate
outer parent passed, collected without signals or remaining owned process
groups. All 338 live inputs, the 247-file private copy and built resources were
unchanged, and the dedicated simulator was Shutdown before, after and at a
fresh root check. An independent Astra actual-result review confirmed the
strict collection. The first whole-case elapsed value was 2,681 ms; later
canonical cases ranged from 2,053 to 2,417 ms. These simulator observations
include validation/copy/provider work and different cache contexts; they are
not physical-device or isolated-inference benchmarks. The sky miss and all four
earlier setup failures remain preserved, with no recognition rerun or tuning.

- [Fixed 17-case actual checkpoint](../../work/r-inference-checkpoint-20261012/restart-native-ai-v1/CHECKPOINT-native-public-coverage-actual-v1.json)
- [Fixed 17-case independent actual review](../../work/r-inference-checkpoint-20261012/restart-native-ai-v1/ASTRA-NATIVE-PUBLIC-COVERAGE-ACTUAL-v1.md)

The Release mirror candidate has been reviewed as source but remains unapplied
and unverified in that configuration. The cached phonetic model remains a
separate research route. Its C normalization arithmetic passed the fixed
numerical checks, but the full Python/Core ML parity attempts crashed without a
complete receipt. A reviewed standalone Swift diagnostic compiled successfully;
its model compilation and calls are still pending. Those results do not supply
independent produced-phone labels or establish mobile phonetic accuracy. See the
[Swift readiness record](../data/native-swift-prefix-readiness-20261013.md).

Apple's English simulator assets were installed and reserved. The modern native
Speech probe observed empty input formats and nil selectors, then threw a typed
no-model error; its cause remains unknown. A later legacy en-US capability check
established recognizer availability and on-device support. Its actual recognition
attempt observed denied speech authorization and created no recognition task.
These separate observations do not establish successful Apple recognition. The
working bundled Core ML route is separate. See the
[Apple verification record](apple-ondevice-recognition-verification-20261012.md).

The latest guided-flow check passed all 23 selected unit tests and all 14 UI
journeys, with Debug and unsigned Release builds successful. It changed only the
automated scrolling helper; production behavior remained unchanged. See the
[guided-practice verification record](native-guided-practice-verification-20261012.md).

Word matching does not identify a produced phone or establish pronunciation
correctness. Independent produced-phone/error references, child accuracy,
physical recording/playback/camera behavior, device performance, professional
final review and justified release claims remain open. The consumed once-only
PERCEPT-R study failed before prediction lock and produced no assessment result;
it will not be retried or used to support learner findings. See the preserved
[failed-attempt report](../../work/r-inference-checkpoint-20261011/FAILED-STUDY-v1.md).
