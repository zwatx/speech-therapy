# What to do after an unmatched practice check — October 25, 2026

Selected practice now adds this short cue beside an eligible latest no-match or
uncertain observation:

> A word match isn’t required. You can move on or record another try.

This is decision support, not a new speech finding. The existing interface already
keeps each word-check observation with its recording and supplies listening
focus. The new sentence makes the optional nature of a word match visible at the
point of choice, rather than requiring the learner to open About word checks.
It adds no panel, action, state, recognition, classification, or continuation policy.

## Exact eligibility

The observed row, checked recording, and latest retained take must all have the
same nonnil identity. The current check must be settled with the same admitted
status as the row, and the selected-practice visit must match the current entry.
The cue appears only for notMatched or uncertain, while both actual actions admit:
continuation uses the same coordinator eligibility and screen navigation lock as
Next word; retaking uses the existing canRecordAnotherTry gate. Source review
caught and corrected the additional navigation lock before any test execution.
An unreleased camera owner must not leave “move on” promised while its button is
disabled. No new camera behavior was exercised to verify that mapping.

Earlier or stale takes, unchecked replacements, first review/recheck, free
practice, matched or technical-failure results, and blocked actions do not qualify.
Recording-quality requirements remain unchanged; the cue does not tell a learner
to bypass them. Timeout retains its existing explicit retry action.

## Actual checks

Fresh Debug projects used canonical sources on the owned iPhone SE (3rd generation),
iOS 26.2 simulator. Root personally observed these exact outer completions:

| Group | Result | Observed test / export / verifier |
| --- | --- | --- |
| Presentation eligibility contracts | 3 passed, 0 failed | 20263 / direct export chunk0234e2 / 23830, all exit0 |
| Generated normal/largest UI | 2 passed, 0 failed | 53609 / 84585 / 20553, all exit0 |

The three pure tests cover all six settled statuses; both eligible statuses across
all selected-practice/continuation/retake gate combinations; and missing,
earlier, mismatched, and stale observed/check/latest identities. These prove the
presentation contract, not every native owner state.

The two UI journeys use the unchanged generated wordGuess / wordGuessAX fixture.
Their actual word outcomes are notMatched; uncertain is covered by the pure
contract tests, not a new UI/model experiment. Each journey checks:

- First-review no-match has no cue.
- Selected practice's first checked take has one cue beside its result, with both actions enabled.
- Recording a replacement removes the cue; the earlier no-match remains with its own row.
- Checking the latest replacement restores exactly one cue beside the latest result.
- Explicit Continue saves one Ball participation; fresh recheck's no-match has no cue.
- Public Close removes all four generated files: four made, zero kept, four fake permission requests,
  zero playback starts, pending0/borrowed0, and exactly one `[b:1]` history row.

Normal UI passed in 89.531 seconds; largest text passed in 209.972 seconds.
The unit worker54585 finished normally in 63.097 seconds; UI worker57200 in
346.998 seconds. Owned stages report no signals, remaining process-group rows,
or cleanup errors. Both tracked simulators finish Shutdown. Official results
have no skipped/expected failures, testFailures, or runtimeWarnings; raw compiler
and SDK diagnostics remain retained. This does not claim a warning-free build.

The result verifier checks 308 frozen input pins per group, exact selected test
starts/terminals, twelve UI state markers, and current canonical namespaces.
It verifies40 prior build maps for unit and41 for UI, including the exact completed
unit build. The fresh unit namespace has1690 files; UI has1269. All previous builds
remain inert; no copied build database is executed.

There are21 UI PNG members /17 distinct hashes, including complete cue captures at
both sizes and initial/recheck/retake/Close states. Actual pixel/AX/geometry review
is retained separately under work/word-check-decision-20261025. Root also personally
viewed the normal first cue and largest latest cue. Full paragraph reading and
source assertions are separate from speech-accuracy evidence.

## Preservation and limits

Before copies and executed snapshots bind the exact four changed source/test
files. The preceding reminder-continuity delivery, its1561 artifacts and original
adverse observations stay preserved. Its Player and README current bindings are
intentionally superseded through exact before copies; historical binaries and
receipts are not silently requalified by new source.

Generated capture/recognition providers exercise presentation and ownership with
no real microphone, audio output, network, or inference. Runtime uncertain,
quality-blocked, pending/cleanup, active-mirror, free-practice, playback, VoiceOver,
physical-device, ordinary Release, and clinical behavior were not newly exercised
here. Source admission and pure gates are not substitutes for those checks.
There is no new shipping candidate or installed-byte claim. Historical candidate5
demo / candidate6 limited-QA roles and open audit/reviewer/reference dependencies
remain unchanged. The broad app-completion goal remains active.
