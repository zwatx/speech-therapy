# Home and About layout verification — October 24, 2026

Today now separates the weekday and About at accessibility text sizes: weekday
on its own leading row, About trailing below it. Standard text keeps one row with
a minimum sixteen-point gap. Native fonts, colors and real weekday content are
preserved. The weekday can grow vertically. Header placement stays outside the
existing Home scroll viewport.

About now has a fixed plain Done header above its existing NavigationStack.
Regular vertical siblings allocate space to the header and content. The button
uses the native subheadline style, an internal minimum 44-by-44 frame and a
rectangular content shape. The existing rule, canvas and ink roles are reused.
Dismissal and About contents/links are preserved; navigation bars are not globally
hidden. Deeper Debug-only About routes are source-preserved, runtime-unverified.

## Actual current-source verification

Evidence is retained in `work/home-header-20261024/`. The final ordinary Release
run is **release-checks-v6**, root outer **67087/0**, on the owned iPhone SE3/iOS26.2
simulator. It builds canonical app/UI sources in a fresh project/DerivedData with
Release testability/debug dylibs/coverage disabled. Both 360-second journeys pass:

| Method | Duration |
| --- | --- |
| `testReleaseHomeHeaderRemainsReadableAndUsable` | 46.605 s |
| `testReleaseLargestTextHomeHeaderRemainsReadableAndUsable` | 56.175 s |

Official results show two passed, zero failed/skipped, and no runtime warnings.
Raw logs contain exactly two starts/two passes with no restart. Build logs retain
SwiftShims debug-information path and unused AppIntents metadata warnings; this
is not a claim of a warning-free compiler build. SDK child43612 completes normally
in178.351 seconds, with no owned-group residuals, signals or cleanup errors.
Direct result export completes0. Root observes every outer terminal.

The journeys check one real Saturday weekday and About control, their geometry,
full-window visibility and About's enabled/hittable 44-point minimum target.
Home header and viewport frames remain unchanged after a measured pan. Normal
Home fits and moves0; largest Home overflows and its title moves105.5 points.
No overflow is invented for a fitting screen. Pans use observed blank gutters.
About's actual title/privacy body exist; About opens and Done dismisses correctly. The full
initial title is hittable, finite, inside the window and below Done before any
About scroll. Ordinary ball practice and default guided setup open/close without
media, and Sounds/Progress/Today return preserves visible history identifiers.
This does not inspect the underlying history file.

Measured final About geometry, in a375-by-667-point window:

| Text size | Done x,y,w,h | About title x,y,w,h | Scroll viewport y,height |
| --- | --- | --- | --- |
| Standard | 307,38,44,44 | 24,107,221,41 | 83,584 |
| Largest accessibility | 239,38,112,58.5 | 24,121.5,206,142 | 97.5,569.5 |

Both titles start25 points below Done's bottom and24 points inside the content
viewport. Initial/after-pan/returned Home frames agree. Actual independent Astra
review covers all35 unique PNG groups/48 hash-verified members across retained
attempts, including all11 new final groups, plus40 measured geometry records.
The final titles and Done glyphs are complete and separated; no unintended empty
navigation-bar gap is observed. Privacy-body existence does not establish full
body visibility in the initial screenshot. Real-date captures do not qualify all
weekdays/locales, intermediate text sizes, VoiceOver or unrelated contrast.

## Preserved failures and corrections

The earlier Saturday/About image demonstrated crowding, with both strings
apparently whole; original glyph clipping was not established. All attempts remain:

- v1: zero tests; the new test's nested async teardown captures a non-Sendable
  XCTest case. The installed explicit synchronous MainActor overload fixes it.
- v2: two failures; XCTest rejects a privacy string subscript longer than128
  characters. An exact full-label predicate preserves the complete assertion.
  Neutral foreground teardown capture also avoids unpublished failure counts.
- v3: both fail the unchanged44-point Done gate; actual toolbar targets are36high.
- v4: a framed native toolbar label still exposes36high. That attempted repair
  is retained, not reported as a fix.
- v5: both functional journeys pass, including actual Done44-by-44/112-by-58.5.
  Actual screenshot review finds the outer safe-area inset hiding the initial
  About title at both sizes. It is not a visually clear candidate.
- v6: explicit header/content siblings and a stronger initial-title check pass
  both complete journeys; actual final pixels resolve the observed occlusion.

There are ten actual method executions across v2–v6: four passes and six failures.
Only the two v6 passes qualify current source. No assertion, touch requirement or
360-second journey bound was relaxed. No new contrast audit mask is used.

## Frozen simulator candidate and boundaries

Candidate **practice-demo-20261025-simulator-1** binds the exact final source/UI
and all26 built app files (309,917,359 bytes) in `CANDIDATE.json`. After tests,
a lookup while Shutdown returns149; it is preserved as an unavailable comparison.
A separate bounded owned-simulator boot/read-only app-bundle lookup compares all26
installed files byte-for-byte with the candidate, then shuts down. Root outer
**11375/0** observes success; it launches no app and reads no app Data or media.
The protected simulator is only listed and remains Shutdown. All19 older build
namespaces are preserved; no copied build database is executed. Process/RSS/disk
checks are sampled, not complete SDK/service closure guarantees.

No real microphone, camera, playback or word-model action is selected in these
journeys. Existing Home contrast failures, real-media rehearsal, sound-level
assessment reliability, clinical validity and VoiceOver qualification remain open.
A short human rehearsal/fallback is in `DEMO-SCRIPT.md`; its voice steps have not
been performed by this verification. Word observations/general guides are not
independent sound-error detection or diagnosis.

A separate bounded phone info query establishes a connected developer tunnel
and available services, not media readiness. An all-category installed-app query
returns130apps and no matching learner bundle. The canonical target has no selected
development team/profile; this candidate is a Simulator product. Phone signing/
installation approval is pending. No account/security/signing change, install,
private recording upload, research rerun or new external message occurs here.
