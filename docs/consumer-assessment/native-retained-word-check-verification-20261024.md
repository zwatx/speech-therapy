# Retained recording word-check observations — October 24, 2026

A learner can keep and replay two recordings, but previously only the latest word
check remained visible. Recording another take cleared that display even while
the checked recording remained playable. Each retained recording now carries its
own admitted whole-word observation.

## Resulting behavior

- **This try**, or **Earlier try / Latest try**, identifies each playback row.
  The admitted match, no-match or uncertain outcome appears below its own button.
- An empty row says “No word-check result for this try.” Absence does not claim
  the recording was never submitted: cancellation or processing failure can also
  leave no admitted outcome.
- A fresh recording does not inherit an earlier result. A third recording removes
  the oldest take and its observation together. A denied or failed replacement
  preserves the surviving observation after explicit return to review.
- If that failed replacement allows another explicit check of the same kept take,
  its newly admitted result replaces its previous snapshot. It cannot leave an
  old match displayed beside a current no-match result.
- Only matched, not-matched and uncertain are retained observations. Timeout,
  unavailable and cancellation remain operational messages. Guessed alternative
  words remain current-only and explicitly say “the latest try” when two exist.
- During checking, transition or uncertain cleanup, row observations are hidden.
  Departure removes them with their take. There is no persistence or additional
  automatic recognition, recording, playback, history write or scoring.

Admission uses the exact request/take, selected prompt and guided visit, confirmed
recognizer cleanup, and post-publication eligibility. Synchronous Close/background
observers cannot resurrect a result. Guided review still freezes the first
submission and disallows another submission in that visit; its ledger is
independent of the playable-take snapshots. Guided practice may retain two
checked takes without changing the frozen first-review record or participation.

## Actual verification

One final **Debug simulator** run passed **49 tests: 45 unit checks and four UI
journeys; zero failed, skipped or expected failures**. The dedicated iPhone SE
(3rd generation), iOS 26.2 simulator was used. This is current production source
with explicitly injected generated capture/playback/recognition dependencies.
It is not real speech, sensor, model-accuracy, physical audibility or diagnosis
validation. No recordings were uploaded or physical device operated.

The focused unit checks cover two checked takes, unchecked replacement, oldest
removal, failed replacement recovery, a new exact check of the same kept take,
sibling and late receipts, unconfirmed cleanup, cancellation, synchronous
Close/background settlement, guided visit changes, and unchanged frozen
first-review/history metadata. Presentation and closed generated-host admission
checks also pass.

| Actual UI method | Duration | Observed behavior |
| --- | ---: | --- |
| Compact retained checks | 25.370 s | Earlier matched / latest uncertain; unchecked replacement; exact replay files; oldest eviction; cleanup |
| Largest-text retained checks | 68.720 s | Same identity journey with accessibility5 text |
| Compact current guess | 25.444 s | Fallible latest-only guess; explicit replay; retake clears guess |
| Compact guided current guess | 80.328 s | Initial review → practice → replacement → fresh recheck; frozen first result and status-only summary/history preserved |

All 17 exported PNGs were visually inspected by the independent Astra reviewer;
the coordinating agent also viewed the four comparison captures. Normal text
shows separate replay/result rows. Largest text wraps complete result paragraphs
without horizontal truncation. A whole row, including its heading and button,
does not fit in one viewport at the largest size; the content is scrollable.
Accessibility trees contain the complete labels. Actual VoiceOver speech/order
has not been tested. The final official result summary records no runtime
warnings; separate Xcode SDK-version/debugger diagnostics remain in the raw log.

The terminal SDK test stage lasted 266.738 s. The coordinating agent personally
observed outer session 27975 exit 0, then export session 5902 exit 0. Every owned
stage ended without signals, remaining group members or cleanup errors. Shutdown
reported already shut down; actual subsequent queries verified the owned and
protected simulators both Shutdown. The protected device was never operated.

## Preserved failures and storage recovery

The successful run does not erase two earlier failures:

1. Run v1 stopped before tests at an optional screenshot attachment-name compile
   error in the new test. A non-optional local name corrected it.
2. Run v2 stopped before tests because the linker ran out of disk space. Its copied
   build database also pruned one original-v1 generated YAML through an inherited
   absolute path. Its controller then failed writing its final ROOT receipt; that
   file is absent, and is not presented as a successful or negative normal ROOT.
   The retained clone had the exact original YAML digest, allowing exact recovery.

Both failed result bundles/logs remain. All 1,255 original-v1 file bindings now
match. Four regular bundled public-resource copies were re-cloned from identical
canonical bytes to recover physical storage; their logical size/hash, mode,
mtime and extended attributes matched before and after. Inodes/storage metadata
changed. No resource was altered or executed, and no previous milestone was
purged. The first resource pilot stopped before mutation because the selected
Python lacked a filesystem-attribute API; the corrected pilot used bounded native
attribute reads.

The stopped v2 build was preserved in a verified 2,323-file inert snapshot. Its
whole old intermediates directory was moved outside the active build path before
creating fresh build state. The copied database was not reused. The final
independent postcheck verified 5,381 frozen input bindings, both archive namespaces,
all 1,255 original-v1 files, all nine current source/test files against executed
inputs, and all 654 Position-filter plus 327 preceding feedback-flow artifacts.
It also independently qualified the controller's otherwise unconditional
fresh-state/archive receipt fields; those fields alone are not evidence.

Evidence is retained under `work/take-bound-observations-20261024/`: scoped source
baseline/delta, both failed bundles, mutation/restoration and sharing receipts,
final official results and 17-image index, independent review and `POSTCHECK.json`.
The final app build product is the Debug product in `checks-v2-DerivedData`; the
successful run is **checks-v3**, not the failed checks-v2 result.

## Limits and next work

This improves listen/retry/compare using already available whole-word signals.
It supplies no individual-sound correctness, error substitution, improvement score
or clinical finding. Real media/VoiceOver evidence, qualified native sound-level
processing, reviewer acceptance/reference protocol and clinical validation remain
open. Closed model parity screens remain closed; no private study was reopened.
The broad app goal remains active.
