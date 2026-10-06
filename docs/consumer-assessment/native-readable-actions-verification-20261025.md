# Readable disabled practice actions — October 25, 2026

Disabled primary buttons now use ink text on the existing quiet border fill, rather
than fading both label and surface. Disabled secondary buttons use the existing
muted text token. Enabled colors and pressed feedback, action eligibility, layout,
fonts, padding, and hit areas are unchanged. Record and text-button styles are
unchanged. The unsupported blanket AA comment was removed. This is a readability
improvement; inactive controls are exempt from WCAG contrast requirements.

The only production change in this increment is
`apps/ios-learner/Sources/DirectPractice/DirectPracticeStyle.swift`, SHA-256
`8cae5239aee6b12fffbad6cdd6d71b2edd0d08acf64da371d34d612570f0e18b`.
The original and exact executed copy are retained in
`work/native-accessibility-20261025`.

## Observed verification

Fresh generated projects compile canonical app sources and use task-local UI
overlays plus existing canonical helpers. The corrected app was compiled with
ordinary Release optimization, without app testability, DEBUG, debug dylib, or
coverage. Execution used the owned SE3/iOS 26.2 simulator only. No recording,
playback, camera, or model operation was requested by these journeys.

| Run | Whole methods | Actual result |
| --- | --- | --- |
| Original word-picker audit | 0 passed, 2 failed | Text clipped warning on search field; later Pig states not reached |
| Standalone native/custom search-label comparison | 0 passed, 4 failed | Both label variants warn at both sizes; diagnostic app only |
| Original independent ready-practice audit | 0 passed, 2 failed | Both entry audits returned; Record-reachable audits reported Contrast on disabled Next word |
| Corrected ready-practice audit | 1 passed, 1 failed | Normal journey passed; largest journey still reports Contrast on the synthetic-voice note |

The corrected run started four unfiltered audits and returned from three. Both
normal and largest pre-audit captures show a dark, readable Next word label on the
quiet fill; both explicit disabled-state assertions succeeded. AX frames were
normal `[24,471.5,327,56]` and largest `[24,510,327,95.5]`, with Disabled preserved.
The normal method also completed public Close and compared visible history IDs
with the initial snapshot. The largest method stopped at its failed audit, before
that exit/history check. Geometry after the first audit does not prove pristine
initial scroll position because the audit itself can move the viewport.

Root observed the same outer test parent 38232 exit 65, export parent 13924 exit 0,
and result recorder 99795 exit 0. Recorder success means the failed result was
recorded consistently; it does not mean the tests passed. Exact starts and
terminals matched both selected methods, with zero skips or restarts and no
result-summary runtime warnings. Raw SDK diagnostics remain retained. The result
verified 307 input pins, 36 prior build namespaces, and 1138 current build files.
The protected simulator remained shut down; normal owner closure and shutdown
were recorded without signals, remaining group processes, or cleanup errors.

## Open findings and limits

The largest remaining Contrast warning maps to “Synthetic voice. Word readings
and accents can vary.” The pre-audit note was offscreen; the failure capture shows
the audit brought it fully into view. Its glyphs are complete. Astra reviewed the
full capture and element crop; the dominant opaque foreground/background pixels
match the existing muted and canvas tokens (nominal contrast approximately 5.24).
This does not establish that the audit is wrong. No evidence-supported note
change was identified; its failed result remains open, without suppression,
palette tuning, hidden content, or a repeat intended to obtain a pass.

Search placeholder glyphs were complete in the earlier captured failures. The
standalone comparison shows the custom accessibility label and parent picker
context are not necessary to reproduce that warning. Its cause is unresolved.
The earlier generator failure is retained separately: it produced no UI results;
the corrected standalone project added a conventional Debug configuration while
still executing Release. No learner source was changed for that investigation.

No claim follows about all-app accessibility, VoiceOver behavior, dark appearance,
disabled secondary states at runtime, clinical validity, sound correctness,
recognition accuracy, or live media. Historical Home contrast findings remain
open. The corrected local QA artifact is candidate 6; candidate 5 remains preserved
as fallback. Neither current installed bytes nor physical audibility were checked.
Rights/reviewer replies remain external dependencies, and the overall app goal
remains active.

## Evidence

`work/native-accessibility-20261025/practice-ready-v2/release-checks-v1/OBSERVED-RESULTS.json`
records the actual one-pass, one-fail result. That folder retains the raw log, xcresult, export,
screenshots, AX snapshots, input hashes, generated project, and owner receipts.
`practice-ready-v2/RESULT-REVIEW.md` records independent visual review.
`CANDIDATE.json`, `POSTCHECK.json`, and `DELIVERY.json` bind the app inventory,
preservation checks, source, this report, and retained failed investigations.
