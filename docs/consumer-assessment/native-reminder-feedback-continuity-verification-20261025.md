# Reminder reading during delayed word feedback — October 25, 2026

Selected-practice review now places its existing collapsed **Practice reminder**
ahead of changing word-check, listening, and replay content. When a learner opens
it, arriving feedback no longer grows above the text being read in the verified
configurations. The same canonical instruction, disclosure state/reset rules,
buttons, media ownership, recognition, and participation behavior are retained.
The tradeoff is that the reminder is farther from the retake control. No forced
scrolling, reserved blank area, smaller type, or new content was added.

## Demonstrated problem and fix

Two initial generated UI methods passed semantic persistence assertions, but
actual passive screenshots showed lost reading position in all four transitions.
The largest text moved entirely below the usable viewport. Passing tests did not
make that presentation acceptable. Original results, images, executed sources,
and build namespace remain preserved in `work/reminder-feedback-continuity-20261025`.
`V1-FROZEN.json` binds 661 original evidence files; its SHA-256 is
`4663c83131a7983e716dfd828323429584ea7f171176cdff03a4349bcd2b43f0`.

| Text / result | Original reminder movement | After the fix | Previously visible text retained |
| --- | ---: | ---: | --- |
| Normal / timeout | +174.5 pt | 0 pt | Yes |
| Normal / matched retry | +144.5 pt | 0 pt | Yes |
| Largest / timeout | +577 pt; entirely offscreen | 0 pt | Yes |
| Largest / matched retry | +514.5 pt; entirely offscreen | 0 pt | Yes |

The regression now requires the after content-coordinate visible interval to
contain the entire nonempty before interval, allowing 1 point for rounding.
It permits additional visible text and does not require zero screen displacement;
zero was the actual observation. Exact result and pending/borrow counters settle
before the after capture. No gesture or helper reveal occurs between paired
captures. Offline evaluation of this invariant rejects all four original pairs;
that evaluation is not a second XCTest execution against the old app.

## Actual verification

A fresh Debug project compiled the canonical sources and ran two selected methods
on the owned iPhone SE (3rd generation), iOS 26.2 simulator:

- `testCompactPracticeReminderSurvivesHeldCheckAndTimeoutRetry`: passed, 84.775 seconds.
- `testLargestTextPracticeReminderSurvivesHeldCheckAndTimeoutRetry`: passed, 182.710 seconds.

Both first hold request 6 until a generated timeout, then retry request 7 against
the same retained take with a new operation, ending in a generated word match.
The frozen first-review observation and exact canonical P instruction persist.
Six generated files are made, one kept during practice, and no playback starts.
Checks settle to pending 0 / borrowed 0. Public Continue produces one exact Pig
practice receipt; fresh Ball recheck has no stale reminder, replay, or result;
public Close leaves zero kept files and one `[p:1]` participation row.

Root personally observed test parent 15223, exporter 72418, and result verifier
25746 terminate with exit 0. Test worker 38069 completed normally in 315.765
seconds, without signalled termination, remaining process-group rows, or cleanup
errors. Both tracked simulator states are Shutdown. Official results report
2 passed, 0 failed/skipped, no test failures or result runtime warnings. Raw SDK
build diagnostics are retained; this is not a diagnostic-free claim.

The verifier checks all eight state markers, eight passive probes/four pairs,
306 input pins, all 39 prior build namespace maps, and 1,263 fresh build files.
There are 63 retained screenshot members / 32 distinct byte hashes. The separate
actual-image review covers passive pairs and full paragraph captures; helper
scrolling used to read a long paragraph is separate from passive continuity.
Current production Player SHA-256 is
`84da0190c0cc7073dcbf7f2121ae0288b48973de04f5259ec7041e185bb1dd6a`;
current reminder UITest is
`55df998edb062de7999312c5d12170e27caca8a97b5a80c4acfe145b7b113f72`.
Before and executed copies are retained under `fix/`.

## Scope and remaining qualifications

These are generated Debug outcomes, with no real microphone, audio output,
network, or speech model. They validate presentation and lifecycle behavior,
not recognition accuracy, target-sound correctness, or diagnosis. The four
settled snapshots do not prove every transient frame or later scroll interaction.
Playback-specific transitions, actual VoiceOver delivery, physical devices,
ordinary Release media, and broader clinical qualification were not run here.
The old retake/word-switch journeys were not rerun; their state/reset code did
not change. The existing ordinary Release no-media route does not enter retained
review and was not repeated as nominal evidence for this fix.

No new shipping candidate or installed-byte claim is made. Candidate 5 remains
the broader verified demo/fallback and candidate 6 remains limited QA; neither
historical binary is claimed to contain this new source change. Existing audit
findings, rights/reviewer dependencies, and closed research outcomes are retained.
The broad app-completion goal remains active.
