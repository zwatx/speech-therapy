# Selected-word presentation and selection — October 9

The native Debug/simulator research app now displays the complete selected Word label below the main word heading. Normal text keeps the existing native menu. Accessibility text sizes use an inline list of the fifteen canonical choices in the existing scrolling page, with **Keep current word** at the top.

## Behavior and scope

Repeated targets remain distinct: first/second B in baby and first/final K in backpack. The selected value wraps without abbreviating the occurrence. Selection uses the existing session setter, which clears old recordings and results when the word changes. Keeping the current word changes only the local chooser state and retains the recording, cue and opt-ins.

The chooser respects existing setup-editable and finalizing guards. Canonical identity is checked in full; selected markers and changes use complete prompt equality. Focus returns only if the control remains eligible after synchronous cleanup. Context, consents, processing, licensed examples, session/media ownership and guided behavior remain unchanged.

## Actual final verification

At final **SOURCE-v4** / **INPUTS-v4**, all **63 distinct affected unit methods passed**, zero failures/skips/expected failures. All **six new generated UI methods** and **seven existing UI methods** passed in two separate groups at those same inputs, with zero failures/skips/expected failures. These are thirteen distinct UI methods, not one combined UI run.

| New chooser journey | Observed coverage |
| --- | --- |
| Normal second B in baby | Actual menu selection, full value/control viewport and changed cue |
| Accessibility second K in backpack | Actual inline selection, full wrapping occurrence and final-K cue |
| Accessibility lower ring choice | Actual selection, full value/control and NG cue |
| Different word with a retained generated take | Actual normal selection clears previous replay through the existing setter |
| Accessibility last treasure choice | All fifteen choice labels exposed to the test; actual last-choice selection and neutral manual cue |
| Accessibility Keep current word | Actual Record/Stop, open/keep, same word/cue/opt-ins and enabled retained replay; no automatic playback |

The seven regression methods cover guided first round → early summary → treasure manual practice → full thirteen-word recheck entry, largest-text ring cue/control reachability, missing example metadata, normal occurrence switching, shared-service cleanup pause with local replay, and both word/sound check orders. Recheck entry is not thirteen recorded recheck items.

Original 60-second default / 90-second maximum allowances and assertions remain intact, with no retry flags. Fixed generated capture/player/responses use no microphone, camera, sockets or acoustic model. All 162 bound inputs stayed unchanged. The dedicated verification simulator was freshly verified and was Shutdown before/after every run.

Generic Release compilation passed without execution. Its generated Info.plist retains the microphone purpose and omits the Debug-only camera purpose. This does not ship the Debug/simulator research chooser or verify physical capture/output.

## Preserved failures and repair limits

V1 and v2 each passed 63 units but their four new UI methods yielded two passes/two failures: largest-text native-popup traversal observed no canonical option span. V2 added a real selected-menu-option readiness wait; it did not solve traversal. The underlying popup cause and manual user failure remain unknown. Their source, results and direct PNGs remain preserved.

V3 changed only accessibility sizes to inline choices. Its six new methods passed, but two of seven old methods exceeded the original one-minute allowance. Direct captures showed progress, not a proven deadlock or exact timing cause. V4 changes only test gesture construction: longer ordinary drags for distant controls, gentle moves near them, always inside the unobscured viewport. The 24-iteration limit, full-target/hittability checks, all test bodies/assertions, attachment behavior and time limits remain unchanged. The complete v4 checks above supply the final proof; earlier passes are not pooled. The two formerly timed-out methods took 51.61 and 54.14 seconds; repeated timing reliability is not established.

Opus 5.5 reviewed seven v3 owned partial viewports with no blocking clipping, overlap or readability finding. The production view is byte-identical in v4; that historical review is not a claim of a v4 pixel review or full accessibility audit. Actual v4 direct captures are separately hash-bound. No all-fifteen-selection, full guided pixel journey, VoiceOver, dark/contrast, physical audio or clinical proof follows.

## Exact source and evidence

- SOURCE-v4: 159 rows / 148 Swift files, row digest `f3e7290f94e46bba22eb30d97f2f47ee3c45e7ca5219a575f1983fd80fb415ab`.
- INPUTS-v4: 162 rows, row digest `581455bb731f889e68f3d3d061b757a8ec88c0b159b870e36b2ee1e049639f04`.
- Only [ResearchFeedbackView.swift](../../apps/ios-learner/Sources/Assessment/ResearchFeedbackView.swift) and [ResearchUnifiedFeedbackUITests.swift](../../apps/ios-learner/UITests/ResearchUnifiedFeedbackUITests.swift) change from the earlier focus checkpoint. Project, catalog, registry, model, contracts and session implementation are unchanged.
- Task receipts: `work/consumer-feedback-20261009/selected-word-presentation/` — exact source/input manifests, UNIT/UI/UI2-v4 SAFE-PROOF and EXIT receipts, Release EXIT/purpose receipt, device Shutdown metadata, direct PNG hashes, STATIC-final-v4, PREEXEC_REVIEW-v4, PRODUCT_EQUALITY-v4, OPUS_VISUAL-v3, final root and independent review. All v1–v3 failed capsules remain immutable.
- The [earlier selected-focus guide](selected-listening-focus-verification-20261009.md) describes its separate historical 48-unit/four-UI checkpoint. Its largest-text selection limitation is closed only by this later checkpoint.

The owner-used browser8809 and predecessors remain unchanged and were not contacted. Browser guidance parity is the next fresh-successor task. Intended-sound guidance does not detect produced-phone correctness or establish useful correction, improvement, visual utility or diagnosis. Independent lawful phone references, intended-user evidence, physical audio, final qualified review and release resources remain open; the broad goal stays active.

