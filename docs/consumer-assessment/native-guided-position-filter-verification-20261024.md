# Guided Position-filter repair — October 24, 2026

The ordinary native word picker now expands Position choices in place. This
replaces the specific nested Menu/Picker that emitted a view-hierarchy warning.
Sound retains its existing native menu. The search-clear button also receives an
explicit rectangular hit shape inside its existing 44-point frame.

## Behavior

Home → **Review, practice, recheck** → change a word → **Position** opens four
native buttons: All positions, Beginning, Middle and End. The selected choice has
a checkmark and selected accessibility trait. Opening/closing changes no filter;
choosing a position collapses the choices, including choosing the current value.
Query, sound filter, duplicate exclusion and canonical selection rules are retained.
Search focus is dismissed on disclosure/selection; Return also retains its existing
keyboard behavior. Cancel leaves all five setup words unchanged. Controls use
wrapping text and at least 44-point label targets. Expansion belongs to the picker,
above the result List whose identity changes with its entries.

No recording, recognition, practice eligibility, result interpretation, save or
history transition changes. This is an interface repair, not target-sound feedback.

## Observed cause and bounded change

The previous ordinary Release log places `_UIReparentingView` insertion immediately
after tapping Position, before Beginning selection. The implementation was a
Menu containing a Picker inside a List in the sheet-hosted NavigationStack.
Replacing that control supplies a falsifiable mechanism; no OS fault was assumed.
The original warning remains preserved under `work/next-feedback-flow-20261024/`.

## Actual verification

Evidence: `work/guided-position-filter-20261024/`. Independent Astra source,
corrective-harness, descriptor-binding and actual-screen reviews are retained.
All tests used the owned iPhone SE3/iOS 26.2 simulator and ordinary Release root.

| Successful method | Actual run | Duration | Provenance |
| --- | --- | --- | --- |
| `testReleaseHomeGuidedSkippedRoundsPreserveObservationsAndHistory` | v1 | 107.951 s | App before the subsequent Clear-search hit-shape correction |
| `testReleasePositionChoicesPreserveSearchAndCancel` | v2 | 59.403 s | App with both product changes; compact journey |
| `testReleaseLargestTextPositionChoicesPreserveSearchAndCancel` | v5 | 127.239 s | Same unchanged v2 app; corrected, separately compiled UI runner |

These are three distinct passing methods across preserved runs, not a single
all-current test execution. The complete skip-only regression did not invoke the
later Clear-search correction. The two focused journeys exercise all four choices,
selected traits, collapse/reset/current-value behavior, query preservation, actual
bread results at three positions, keyboard disappearance, disabled pig duplicate,
Cancel, unchanged five-word setup and unchanged visible Home history identifiers.
Keyboard disappearance may include a scroll gesture's dismissal; source alone
provides the explicit focus assignment. The tests do not independently inspect
the entire history file or establish physical touch at every target edge.

Official exports retain eight method executions: three passed, five failed, zero
skipped. Every run reports an empty runtime-warning array. In particular the exact
old Position → Beginning → All positions interaction no longer records the old
warning. This is scoped to these paths; Sound and other menus are not qualified.
Original failed executions were retained:

1. v1 largest text: page swipes overshot an option; compact: Clear search exposed
   a 13.5-point accessibility frame despite its 44-point visual frame. The AX tree
   separately showed 42 points. Adding label contentShape corrected the actual
   target; a later AX tree records 44×44 and compact activation passes its size check.
2. v2 largest text: new test dispatch read an unrealized result's identifier.
   Checking existence first fixed that test lookup.
3. v3 largest text: a full visible final row at y441–643, within y278.5–667, failed
   an unsupported 40-point extra bottom-clearance requirement. The last row had
   24 points of padding. Requiring full visibility with an 8-point inset fixes
   the false failure without accepting covered content.
4. v4 largest text: page traversal skipped/unrealized the exact pig row and reached
   later pigeon rows. A bounded header reset and measured short scan fix lookup;
   the same pig input and disabled-state assertion remain. Geometry traces and
   unchanged-position/movement limits are retained. Full-width result-row pans
   are native scroll gestures, not claimed empty hit space.

All 20 indexed PNGs were inspected: eight ordinary guided regression captures,
six compact Position captures and six largest-text Position captures. Large type
is visibly enlarged and wraps. Individual choices and filtered word/target labels
are readable in their scrolled viewports; all choices need not fit simultaneously.
Cancel and search stay above the List. Four successful final result traces prove
the target is fully inside the admitted viewport, hittable and at least 44 points
tall; the pig trace ends at y381.5–645 within y286.5–659, before the disabled
assertion passes. Expanded-content pixels do not establish VoiceOver speech.

## Build, binding and cleanup

The first two runs build the actual app and UI tests in optimized Release with
testability/debug dylibs disabled. Later repairs change only test traversal. To
avoid redundant app builds under low disk headroom, v3–v5 each compile only a
standalone UI-test target, then use `test-without-building` against the unchanged
26-file v2 app. Prior builds are preserved.

Xcode's emitted FormatVersion1 descriptor is retained before transformation.
Runner paths use its own Products directory; app library paths use the v2 Products
directory. The documented UITargetAppPath and dependent-product fields name the
existing app. The emitted, undocumented UseUITargetAppProvidedByTests flag is set
false; that interpretation was conditional until the actual ordinary-app launch
and final journey passed. No invented FormatVersion conversion or dummy app is used.
Each descriptor, runner and app input is frozen before execution.

Final audit matches all 342 v5 inputs, all 26 app files and every completed export
input map. Older changed source bindings have exact before-copies. All 327 scoped
artifacts of the preceding delivery remain unchanged. Root observed every outer
terminal; stages closed without signals, remaining owned group rows or cleanup
errors. Shutdown returned 149/already-shut-down; actual final queries independently
confirm owned CA4010CD and protected 132DD629 Shutdown. The protected device was
never operated. Process/RSS checks are sampled, not a complete SDK/runtime closure.

No microphone, camera, playback or word/model check action was selected. No private
corpus/holdout, fitting, signing/account change, upload or new external message was
used. Real media, VoiceOver speech/order, clinical validity and supported learner
sound findings remain separate work. The overall app goal stays active.
