# Complete R/BR guide paragraph captures — October 25, 2026

The ordinary Release R/BR journeys now verify each guide section from its
beginning to its end. This is a test-only improvement. Application code and
educational content are unchanged, and no new production defect was established.
The earlier R checkpoint checked exact section labels with one sampled screenshot
per section; it did not establish continuous coverage of paragraphs exceeding the
viewport.

## Test change

`ReleaseGuidedNavigationUITests.swift` reuses its existing paragraph-capture helper
for the seven R sections. The helper now records an initial frame even when no pan
is needed, refreshes the scroll/window intersection at every capture, and excludes
only Close frames currently intersecting that viewport. Ordinary Close scrolls
with the content; its offscreen frame is not treated as a fixed header.

The test requires finite, nonempty, horizontally contained text geometry and a
visible paragraph beginning. Each subsequent capture must preserve paragraph
size/x, move toward the end, overlap the previous visible interval in paragraph
coordinates and reveal more content. Completion requires the paragraph end to be
visible. At most eight measured gutter drags are allowed. Exact text assertions,
public navigation, reset/history checks and the original 360-second method limits
remain unchanged. No font, content, layout or media behavior was altered.

The executed test SHA-256 is
`75127ae9e9554b51cb76d30724f9662475244f0dc33c01d8a46c84cf855993e7`.
The task preserves its prior bytes and exact test-only delta. The shared helper's
default-guide callers were not selected in this run and are not newly qualified.

## Actual results

Both original ordinary Release R/BR methods passed on the owned iPhone SE (3rd
generation), iOS 26.2 simulator:

| Method | Actual duration |
| --- | --- |
| Largest text, R/BR readability and visit reset | 322.606 seconds |
| Normal text, optional media-free R/BR guides | 146.135 seconds |

The run produced 28 unique completed paragraph traces: seven sections for Bread
and Rabbit at each text size. It retained 37 paragraph screenshot members,
representing 29 byte-distinct images. Three largest-text paragraphs required three
measured pans each: Bread's main detail and R option, and Rabbit's R option. Each
was 683.5 points tall. The minimum actual content overlap was 506.5 points; every
sequence began at the paragraph start and reached its end. These measurements
support continuous capture, not a claim that oversized paragraphs fit one screen.
Independent review opened all 29 distinct raw images and verified all 37 member
hashes, alongside the 28 traces. Complete wording remained readable across the
overlapping sequences, including paragraph beginnings and the final “voice.” line.
The task's `ACTUAL-RESULT-REVIEW.md` and `VISUAL-REVIEWED.json` record that inspection
separately from the geometry proof.

After reading the ordinary Bread/Rabbit guides, the journeys check disclosure
collapse/reopen, reset on another word, guided first review, selected Bread
practice, fresh recheck and return Home. Visible history row identifiers match the
entry snapshot; underlying history-file equivalence is not established by that
assertion. The full paragraph captures themselves are from ordinary practice;
guided stages check ready context and guide title/reset, not every body pixel.

Root personally observed the same outer SDK parent 41017 exit 0, exporter 55949
exit 0 and result verifier 33706 exit 0. The SDK worker 10661 closed normally in
540.276285 seconds. Both selected methods had exact unique starts and passes,
with zero skips, expected failures, restarts or result-summary runtime warnings.
Raw SDK diagnostics remain retained. No owner signals, remaining group rows or
cleanup errors were recorded; the owned and protected simulators were both
Shutdown afterward. The protected simulator was only listed.

The actual app was compiled with Release optimization, without app testability,
DEBUG, debug dylib or coverage. Verification checked 306 frozen input pins, all
37 preceding build namespaces and 1,136 files in the fresh current build. Fresh
generated project/DerivedData paths were used; no copied build database executed.

## Limits and retained evidence

The journeys never select Record, playback, word checking, mirror or external
source links, and perform no accessibility audits. This supplies no microphone,
audibility, model accuracy, VoiceOver, contrast, therapeutic or clinical evidence.
General canonical instructions remain separate from observations of a recording
and do not diagnose which sound a learner produced.

Existing search-field, synthetic-voice-note and historical Home audit findings
remain open. This passing group does not replace those failed results. Sources,
full guided R-body pixels and other guide contexts remain outside this new visual
coverage. No new shipping candidate was created: candidate 5 remains the default
demo and candidate 6 remains the separate limited readability QA checkpoint.
The broader app goal remains active.

All new records are in `work/r-guide-complete-readability-20261025`: source/before
bindings, raw logs and xcresult, exported attachments, `PARAGRAPH-TRACES.json`,
`PARAGRAPH-IMAGES.json`, actual result and visual reviews, build inventory and
final preservation/delivery receipts. Earlier passing and failing investigations
remain preserved. Preparation review caught and corrected stale cloned runner/
exporter paths before any execution; no old output path was reused.
