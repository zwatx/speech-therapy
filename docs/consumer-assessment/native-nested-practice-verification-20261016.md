# Native nested practice navigation

Search and sound-library practice now refresh Home's existing cleanup-recovery snapshot when their practice sheet closes. Both routes use the existing environment callback and the same player/history dependencies. Refresh only reads current recovery state; it does not retry deletion, start media, run a check or save participation. A failed-file dismissal and passive-refresh counters were not exercised in these UI cases; the callback wiring and passive behavior were source-reviewed.

Opening these cards also exposed a SwiftUI runtime warning. Source review identified the lazy mirror observer as a trigger. The mirror's concrete published-state stream immediately emits its current snapshot on subscription. The parent previously forwarded that snapshot as a change during view rendering. The fix skips only this initial notification. Actual mirror transitions still forward synchronously; current state, ownership, exact stop acknowledgments and Close guards remain unchanged.

## Actual verification

On the dedicated arm64 iPhone SE (3rd generation), iOS 26.5 simulator, eight selected Debug unit methods and two ordinary Release UI methods passed once, with zero failures, skips, expected failures or runtime warnings. Official summary/tree/action/method details establish the exact methods, one run each and device/configuration identity. The original strict Release result reader was unchanged and accepted both warning-free cases.

| Group | Actual result | Command / enclosing phase |
| --- | --- | --- |
| Mirror notification and Close/reentry unit cases | 8 passed | 7.050 / 20.743 seconds |
| Ordinary Release nested navigation | Compact 47.774 seconds; largest text 36.003 seconds | 90.535 / 103.415 seconds |

The new unit case observes the real lazy mirror getter: first and repeated reads publish no parent change and return the same instance. Its first actual simulator-unsupported Show transition and following Hide publish synchronously before return. Inert media dependencies remain unused. Seven existing cases retain parent-state forwarding, both audio/camera completion orders, failed camera stop with explicit retry, held audio/camera cleanup and reentrant Close suppression of saving or permission admission. Assertions are distinct from separate machine cleanup receipts and physical media evidence. No separate old-source unit red run was performed.

The compact Release case opens the shoe card from Search, closes to the preserved query, returns Home with native Back, then opens the SH library's shoe card and closes to that same library before returning Home. The largest-text case types television in Home Search and submits Return as separate measured actions, opens the correct /ʒ/-middle card, closes to Search and returns Home. Actual emitted timings are 687.146ms for letters and 578.560ms for Return. All final route/value flags are true. The earlier Home Search stall was not reproduced, so its layout was left unchanged.

Root inspected all eight current PNGs and all three geometry payloads. The compact cards and largest-text television card show the intended word; largest-text letters wrap in the Search field while the native keyboard is visible, then Return dismisses the keyboard. Home images show scrolled portions, not proof of every Home heading or control. This is focused route and visual evidence, not a keyboard-navigation or VoiceOver audit.

The common source/tool map has 256 bindings. Actual compiler commands confirm Debug/-Onone/DEBUG/testabilityYES for the unit host, and Release/-O/noDEBUG/testabilityNO for the ordinary app/UI bundle. Builds took 15.082 and 33.919 seconds, with 48 and 68 built bindings respectively. The app compilation has 102 Swift inputs including generated asset symbols; unit compilation has 11 test inputs and UI compilation one. These counts are not method counts. SDK 27 compiled an iOS 17 deployment target; actual runtime was iOS 26.5. All build/test phases closed normally with Shutdown, no signals, cleanup errors or remaining owned process-group rows. The ordinary full-app Release test ran last; no separate reinstall/container byte audit followed it.

## Preserved failure and scope

The first Release run functionally passed both journeys but emitted the view-update publication warning once per method. Its strict reader rejected the checkpoint. That failed admission, original outputs, screenshots and source map remain unchanged in execution-v1. The successor changes only the session's initial mirror notification within the pinned app inputs; the two UI methods, execution scripts, limits and warning-rejecting reader are byte-identical. The new regression and successor are separately source/result reviewed. Passing successors do not retroactively admit the original or establish a unique framework-wide cause.

Production formatting passed strict lint. The test-file edit is limited to the 56-line regression; its exact preexisting prefix/suffix are preserved. Whole-file test lint still reports 27 identical preexisting findings, with zero new findings; it is not a whole-file lint pass. Before copies, complete four-file patch, formatting receipts, actual results and independent reviews remain in work/native-nested-cleanup-refresh-20261016/.

These navigation cases never activate Record, Check, playback, mirror, Retry or settings. The ordinary app retains its existing startup temporary-file cleanup; generated cleanup isolation is not claimed. Failed-file dismissal, passive callback counters, live capture/playback/recognition and physical camera preview remain separate verification boundaries. Previous recording and Clear results remain historical evidence after this source change.

The broader app goal remains active. Apple English assets and prior on-device capability are established, but Apple Speech authorization was denied before any recognition task started. Bundled word recognition remains the previously verified default. No signing/account settings changed and no recordings were uploaded. Word matching and recording observations do not establish produced-sound correctness, diagnosis or effectiveness.
