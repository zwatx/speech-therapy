# Sunday, October 18 prototype target

Decision recorded October 14, 2026, America/Chicago. The requested demo is real
in-app recording → validated pronunciation judgment → practice → fresh recheck,
across multiple common sounds. Model integration takes priority over UI polish.
The owner explicitly requires validated judgments; experimental model observations
do not meet acceptance. The owner has no additional validation evidence outside
this repository.

**Status: the requested validated demo is not realistically supported by Sunday
on the available evidence.** An engineering review of the existing app journey
is feasible, but is a different, incomplete deliverable. This document does not
replace the requested outcome with that smaller demonstration. A later validated
date remains unestimated until the reference-data and evaluation dependencies
below have an actionable route.

Implementation update: the owner subsequently authorized the same-Mac service
and requested actual integration with judgments disabled. The Debug simulator
guided flow now connects its recording owner to the complete feature/head path,
with explicit opt-in and known age. The [integration report](native-guided-model-integration-20261014.md)
records passing generated lifecycle tests and actual model work separately from
failed native word-admission attempts. The October 15 follow-up passed native
word recognition and the complete model through practice/recheck on two permitted
child-speech files (/p/, /t/); /b/ and /m/ were uncertain. Capture hardware remains
doubled in those passing cases. Two separately authorized production-recorder
attempts captured only the −160 dBFS floor and withheld model processing. Mac
output was subsequently found muted at 0%; the owner chose to keep it muted.
The owner then authorized virtual input and installed BlackHole. Controlled T and N
journeys completed with six actual recorder takes and six real model calls through
practice/recheck; P/B/M/K/L did not pass native word admission. Physical output was
not unmuted. This establishes multi-sound virtual-input engineering integration;
physical microphone behavior and pronunciation validation remain unverified.

## What works, and what that proves

| Part | Existing implementation and recorded verification | Remaining limit |
| --- | --- | --- |
| Recording and listening | Native temporary capture, replay, retry and cleanup; Debug and unsigned Release compilation | Initial silent-input failures are preserved. Explicit BlackHole routing subsequently passed T and N recorder/model/practice/recheck journeys with six fresh takes, six real model calls and cleanup. Physical microphone/playback and Release media runtime remain unverified. |
| Review → practice → recheck | Five unique review words; explicit choice of 1–3 practice words; fresh recheck of the same five; first observations stay bound to the exact entry | Latest saved simulator checks: 24 unit and 14 UI tests passed. The UI evidence uses generated cases and establishes interaction, not pronunciation accuracy. |
| On-device model integration | Bundled Whisper whole-word recognition; real licensed public recordings exercised the native provider | 12 of 13 canonical examples matched; sky did not. Two deliberately mismatched prompts were rejected. These are word-recognition observations, not individual-sound judgments or live child capture. |
| Multi-sound research model | Portable ages-6–12 mixture accepts 23 canonical consonants and preserves occurrences; feature-input export parity exists | Outputs are subjective corpus-rating distributions. These exact fitted weights have no independent pronunciation-correctness validation. ZH is unsupported. |
| Raw audio → multi-sound research output | Existing local research bridge processed a permitted fitting recording with feature/output parity | Guided integration passed native word admission → full model → practice → recheck on file-backed P/T and actual production-recorder virtual-input T/N. The virtual cases made six real model calls. These are engineering replays, with no validated sound judgment or physical-microphone claim. |
| Native phonetic execution | Repaired Swift worker returned two finite, identical synthetic predictions | Original verification timeout is preserved. Separate late observation establishes execution; numerical parity and real-speech behavior remain open. It is not the integrated child feedback model. |

Evidence: [guided continuity](native-guided-continuity-20261013.md),
[bundled recognition](native-bundled-recognition-verification-20261012.md),
[child research model](../model/ages-6-12-model.md),
[local research bridge](../../research/audio-head/consumer_assessment/README.md),
[word-admitted preview](../../research/audio-head/local_wav_prototype/README.md),
and [native phonetic execution](../model/native-input-interface-diagnostic-20261013.md).
These are existing recorded results, not new runs made for this milestone review.

## Integration direction

Reuse the existing native coordinator, recording owner and model paths. Do not
start another UI or training campaign for the deadline. The current guided
defaults span /b/, /p/, /m/, /t/ and /d/; they can exercise the engineering journey,
but do not form an approved assessment pack. The validated subset must be chosen
from actual sound/position/reference evidence before its evaluation, rather than
from whichever examples happen to produce attractive model outputs.

The native phonetic worker returns `[1,199,392]` CTC logits. The child mixture
needs `float32[N,1037]`: 1,024 separate encoder features per target occurrence
plus 13 CTC scalars. Consequently, native CTC parity is only one dependency;
it does not supply the missing encoder-feature, occurrence and rating-head
integration. The existing local research bridge already contains those stages
on the Mac. Its results must remain internal until the required claim is
supported. Same-Mac loopback processing was subsequently explicitly authorized
for this prototype and is now integrated; external recording uploads and
physical-device work remain outside the authorized route.

## Critical path and review checkpoints

The dates below are planning checkpoints, not completed work or a promise that
independent validation can fit into four days.

| Checkpoint | Work and reviewable output | Completion condition |
| --- | --- | --- |
| Thursday, October 15 | Resolve the model/evidence route first. Map a bounded sound/position pack to the exact candidate, intended users and qualified reference labels. Reuse the existing annotation/content workflow. | Identify permitted independent evaluation data and qualified reference judgments, and define decision/abstention criteria before examining evaluation outcomes. If unavailable, report the validated milestone blocked immediately. |
| Friday, October 16 | Review the now-integrated same-Mac feature/head path, actual virtual-recorder T/N journeys and all admission/timeout failures. Native CTC port/parity is outside this prototype critical path after the same-Mac route was explicitly approved. | Preserve exact evidence and source/model bindings; characterize startup latency and additional supported inputs without changing admission thresholds or claiming accuracy. The current transport budget is 90 seconds server, 100/105 seconds client. |
| Saturday, October 17 | Review the integrated build and prepare the bounded demonstration using permitted fixtures and explicit virtual routing. T/N complete journeys, P/B/M/K/L abstentions, generated binding checks and real cancellation evidence are already recorded. | Demonstrate the actual engineering behavior with judgments disabled; do not treat these selected training replays as an independent evaluation or new productions. Cold-start behavior under the longer budget, physical-microphone behavior and validated sound judgments remain separate limits. |
| Sunday, October 18 | Review the actual build, reproducible journey, model/evidence versions, all attempted outcomes and unresolved gaps. | Call the requested milestone complete only if both integration and independent pronunciation validation support the judgments shown. Otherwise deliver an explicit incomplete engineering review. |

Validation remains a separate dependency from implementing these checkpoints.
For the intended ages 6–12 and selected sounds/positions, the evaluation needs
independent qualified correct/incorrect/uncertain references, appropriate
speaker/prompt/capture and acceptable-variant coverage, fixed judgment and
abstention rules, per-sound false-correction/missed-error/coverage results with
uncertainty, and reviewed feedback wording. Recheck can show paired observations;
claiming improvement additionally needs measurement-reliability evidence. No
numerical clinical acceptance thresholds or reviewer approvals are invented here.
Use the [assessment specification](assessment-v1.md),
[existing SLP handoff](../model/slp-handoff.md) and
[pending content worksheet](proposed-engineering-pack.md).

## Constraints and acceptance

Keep pronunciation judgments disabled while evidence is missing. Whole-word
matches, dictionary targets, fitted corpus-rating probabilities, training replay,
synthetic parity and UI tests cannot substitute for validated sound judgments.
Preserve the failed once-only PERCEPT-R study and untouched reserve; do not
retry, refit against, unseal or repurpose them to meet this deadline.

Existing simulator-only, local-audio, no-external-upload and no-outreach constraints
remain in force; explicit same-Mac processing is permitted. The validated-feedback requirement exposes an unresolved dependency
on qualified labels and review; the earlier deferral of professional review has
not been silently treated as evidence or approval. No signing/account changes,
publication, deployment or participant collection occurred for this review.

The Sunday report must state separately: what ran with genuine audio, what was
generated or source-only, which sounds/positions actually received supported
judgments, all unavailable/failed attempts, runtime and cleanup observations,
and what still prevents the requested acceptance. A runnable engineering demo
does not close the validated milestone.
