# Selected-practice instruction — October 24, 2026

Scoped behavior and visual checks pass. The broader app goal remains active.
This is general practice guidance, not a detected pronunciation finding.

## User behavior

Previously, selected practice placed Record before a collapsed optional guide.
A learner could complete practice without opening a concrete instruction. This
change is a deliberate teaching improvement, not a demonstrated runtime defect.

Ready selected practice now places **Try this** and the selected target's existing
short guide before Record. B/P/M/T/D, initial R and BR reuse their canonical guide
text. A canonical target without a guide receives only current-word rehearsal:
“Say ‘word’ as one whole word. Record a try, then play it back.” Initial review,
fresh recheck and ordinary practice do not receive this new inline instruction.

Expanding About while the inline instruction is shown omits only the duplicate
short detail. The guide title, illustrations, R alternatives/accent context and
Sources remain. When the inline instruction is absent, the guide retains its
original detail. Its disclosure identity continues to reset on word/visit changes.

## Identity and scope

The pure `DirectPracticeInstruction` helper admits a typed practice visit matching
the prompt entry, canonical sound/symbol/position and complete canonical prompt
metadata. It accepts no recognition result. Arbitrary old same-entry workflow
UUID freshness remains the existing full prepared-visit caller gate's job; these
new helper tests do not establish that property independently.

The player shows the instruction only in managed ready practice, excluding the
recording-startup-unavailable branch that does not render the ready controls.
No recording, check, replay, completion, ledger, history, cleanup, model, content
source or persistence contract changed. A stable padded-prompt anchor and
`ScrollViewReader` now position a fresh exact selected-practice visit at its word.
The observed key excludes phase, observation and disclosure state. There is no
new session reset, animation, asynchronous scheduling or media action. Frozen
first-review context remains available above the prompt. The existing guide text
and attribution are reused without modification.

## Focused behavior checks

Before the UI-only visit-positioning correction, the fresh Debug app/unit project
passed **23/23** selected methods: seven new instruction tests, nine guide tests, three ledger tests, two session tests and
two generated coordinator tests. Raw logs have 23 unique starts and passes and no
restart; the official result has no failures, skips or runtime warnings.

New tests cover exact default guidance, initial R versus BR and B in bread,
unsupported K fallback, nil/review exclusion, mismatched entries, forged prompt
metadata/symbol/position/session and changed-word recomputation. Existing generated
regressions cover exact fresh practice take/save/cleanup, frozen first-review
timeout/context and same-five fresh recheck. Their injected capture/recognition
paths establish contracts, not real microphone or model performance. The helper,
guide, unit tests, session and ledger bytes remain unchanged for v2; these are
v1 unit results, not a second unit run against the revised player.

Root personally observed unit outer 42563 exit 0 before exporting. The SDK stage
completed normally in 69.861 seconds with no process signals, residual group rows
or cleanup errors. Both owned and protected simulators were Shutdown at the
before/after listing gates; only the owned device was a test/shutdown destination.

## Ordinary Release screen checks

V1 passed both methods: largest 285.383 seconds and normal 120.353 seconds, with
no failures, skips or runtime warnings and no restart. Root personally observed
outer 83080/0 and export 64342/0; SDK 479.421 seconds completed normally with no
signals, residual group rows or cleanup errors. All 31 distinct PNGs (37 members)
and 26 geometry records were independently inspected. Text was readable across
overlapping captures, but both bread-entry screenshots exposed a product gap:
the new target/instruction remained above the retained scroll offset while Record
was already visible. The passing test scrolled upward before checking readability.
V1 remains preserved functional evidence, not automatic-entry exposure proof.

V2 adds passive pre-gesture word-containment checks for both pig and bread, plus
immediate before/after disclosure checks that forbid jumping back to the word.
Both final methods pass: largest 257.579 seconds and normal 123.384 seconds, with
no failures, skips or runtime warnings and no restart. Root personally observed
outer 88619/0 before export 15394/0. SDK 456.691 seconds completed normally without
signals, residual group rows or cleanup errors; 22 prior namespaces were verified
and both simulators were Shutdown at the listing gates. Independent review
actually opened all 46 distinct raw PNG groups, verified all 56 member hashes and
recomputed all 44 geometry records. No new blocking readability finding remains.

All four pre-gesture entry checks passed. Largest pig/bread word frames begin at
y 103.5 with height 147, inside usable viewport y 86.5–659; normal pig begins at 174
and bread at 89, each height 86, inside y 72–659. Root also viewed all four entry
PNGs and three instruction frames: the new target is recognizable immediately,
with natural overflow at largest text. No test scroll precedes entry proof.

Eight same-visit disclosure pairs retain the word above the viewport and keep
the expanded control reachable. Their actual recorded word/control positions
are unchanged before/after; no corrective test scroll follows the tap. Fourteen
title/paragraph sequences cover complete instructions, P attribution/license and
restored recheck detail. Twelve fit one frame; largest BR and attribution each
need three overlapping frames, ending at 658.5 and 657.5 within viewport bottom 659.
Partial adjacent text at a deliberately scrolled edge is natural viewport crop,
not permanent glyph clipping. The complete R explanation is not claimed.

Both frozen journeys have 360-second allowances and use the ordinary app without media/test fixtures at
standard and largest accessibility text sizes. They cover ordinary/initial/recheck
exclusion, pig→R-middle-bread instruction replacement, instruction-before-Record,
deduplication, complete P source/license paragraphs, source-link targets, restored
recheck guide detail, summary/Close and unchanged visible history identifiers.
No Record, Hear word, replay, check, mirror or external-source link is activated.

## Build and preservation boundaries

Fresh generated projects use the canonical source/resource/package paths. Build
phase admission requires the new helper and respective new test exactly once in
their expected targets. The stale canonical `.xcodeproj` was preserved, not used
as evidence that it independently admits the new helper; `project.yml` includes
the complete Sources directory. Signing/account settings were not changed.

The unit controller preserved 20 prior build namespaces; the v1 Release controller
additionally preserves the completed 1,690-file unit build. The v2 controller adds
the completed 1,132-file v1 Release build, for 22 prior namespaces. Original
unit controller/manifest inputs remain unchanged. Source/test snapshots, exact
input pins, result bundles, exports, independent reviews and final preservation
receipts reside in `work/quality-loop-20261024/`.

Root owns serial SDK/export operations. The owner bounds individual process
groups with sampled RSS/disk checks and stage deadlines. Synchronous hash audits
are not a hard whole-parent deadline, and sampled observations do not prove full
implicit SDK/service closure. No copied build database is executed.

## Limits and next work

This increment does not establish sound correctness, diagnosis, improved speech,
real-model accuracy, physical audibility/capture, VoiceOver or whole-app release
qualification. Historical Home contrast findings remain open. Phone installation,
signing and physical-media work remain cancelled. No private/participant/holdout
data, closed-study rerun, model tuning, upload, new outreach or publication occurs.

The next prepared enhancement is explicit retry after a cleanup-confirmed timeout
on the kept take in ordinary or selected word-only practice. It is not a
demonstrated bug or measured timeout-frequency claim. The settled design includes
an explicit provider capability so the research adapter remains excluded from new
timeout retries. First-review and recheck submissions must remain frozen; no
automatic retry is proposed. No retry behavior is implemented in this increment.
