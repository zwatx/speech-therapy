# Ordinary Release guided navigation and accessible word picker

October 15, 2026. The ordinary Release app now has executed UI coverage from Home through guided setup, manually chosen practice, recheck, paired observations and Home again. These journeys use explicit skips, not generated recordings or invented recognition results.

The first runs exposed two largest-text picker defects: Cancel text was clipped in the native toolbar, and the selected position label was vertically clipped. An actual tap 21 points above Cancel's center did not dismiss the picker. Moving an icon and its hit shape inside the toolbar label improved rendering but did not fix that sampled tap.

The final picker uses the app's existing sticky Close-header pattern for Cancel, below the native navigation title. Its growing text and rectangular hit shape are inside the button label. The two native filter menus retain their existing Picker options, tags and bindings, with selected-value labels that can wrap fully. No text-size cap or font shrinking was added. Recording, recognition, ledger, model and scientific thresholds were unchanged.

## Executed checks

| Current-source Release UI case | Result | Case duration |
| --- | --- | --- |
| Compact: picker position selection/reset; five first-review skips; explicit pig selection; practice skip; five recheck skips; paired observations; Done/Home; fresh setup/Close | Passed | 114.759 seconds |
| Accessibility XXXL requested: setup; two sampled Cancel taps with confirmed dismissal; first visit; reachable Record and Close/Home | Passed | 51.232 seconds |

The official result contains exactly these two methods, with zero failures, skips or expected failures. The enclosing run and Xcode child exited zero after 209.601 seconds including build and cleanup. All 216 pinned inputs stayed unchanged and current. Actual SwiftDriver commands show the app and UI-test module both optimized with `-O`, without `DEBUG` or `-enable-testing`; both built app and UI-test Mach-O binaries contain only arm64. Testability and signing were disabled. The dedicated compact iOS 26.5 simulator returned to Shutdown, and a separate exact-build-path scan found no owned compiler workers or required signals.

The saved touch attachment records Cancel's accessibility frame as 327 × 58.5 points. Taps at its center plus vertical offsets −21 and +21 each required the picker navigation bar to disappear and the original setup button to become hittable. These are two sampled interior points on the replacement control, not proof of its entire hit rectangle or general accessibility conformance. Earlier failures reached only the upper probe; the lower point had not been tested.

Root inspected the [largest-text picker](../../work/release-guided-navigation-20261015-v4/attachments/631BE6B0-59D4-4CB0-B808-05F8AD2F29BC.png), [ready recording screen](../../work/release-guided-navigation-20261015-v4/attachments/3A93CDEF-1D96-4C7D-BF1D-596263FF1D76.png) and compact setup. Cancel, All sounds and All positions render fully in the picker image. Long content is presented in a scroll view. A screenshot of one scroll position does not prove every control is simultaneously visible.

The [verification aggregate](../../work/release-guided-navigation-20261015-v4/verification.json) summarizes the result, compiler flags, numeric touch observations and root closure. Exact [source pins](../../work/release-guided-navigation-20261015-v4/release-input-pins.json), [selected methods](../../work/release-guided-navigation-20261015-v4/methods.json), [official results](../../work/release-guided-navigation-20261015-v4/release-summary.json) and [seven attachment hashes](../../work/release-guided-navigation-20261015-v4/attachment-pins.json) are retained alongside it in the task directory. The new Release-only UI suite passes strict Swift formatting lint. The production view retains exactly one pre-existing line-length diagnostic on unchanged line 347; no changed-line diagnostic was added.

## Preserved earlier results

| Attempt | Official result | Observed failure |
| --- | --- | --- |
| Original navigation suite | 1 passed / 1 failed | Cancel accessibility frame measured about 36 points, before any dismissal tap |
| Native toolbar touch probe | 1 passed / 1 failed | Upper sampled tap did not dismiss the picker |
| Toolbar icon and wrapping filter labels | 1 passed / 1 failed | Filters rendered fully and position selection/reset passed; upper sampled Cancel tap still missed |

These attempts remain in `work/release-guided-navigation-20261015/`, `-v2/` and `-v3/`, including frozen source and official results. All returned the simulator to Shutdown with unchanged inputs and no remaining owned compiler workers. The final pass does not erase their failures.

## Scope

This is automated execution of the ordinary Release root through native XCTest UI automation, not the generated Debug host or a manual CUA journey. CUA could not select Simulator; that initial route was abandoned before app installation or UI interaction. The task project includes the actual app and this UI suite, excluding the unit-test target. This does not repair the previously failed optimized-unit-test/universal configurations or establish a shipping archive.

The tests never activate Record, Check, playback, mirror, history Clear or permission controls. History comparisons cover only identifiers exposed on Home, which shows at most the latest three rows; full stored history identity was not measured. The category is requested through the normal launch argument, not introspected by production instrumentation. All filter options, keyboard/VoiceOver behavior and a complete accessibility audit remain outside this check.

Live Release media, physical-device behavior, sound correctness, treatment benefit and diagnosis remain unverified. The earlier [actual bundled-recognizer journey](native-release-word-verification-20261015.md#release-guided-coordinator-continuation) is a separate frozen-source milestone and was not rerun for this view change. No microphone/camera operation, recording upload, signing/account change, reserved-data access or model run was performed for this checkpoint. The broader app goal remains active.
