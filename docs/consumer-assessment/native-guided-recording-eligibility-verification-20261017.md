# Guided recording eligibility after cancellation

The mobile Record control now uses the same eligibility rules as the recording
action. After background cleanup removes a take whose first guided review was
already submitted, Record stays disabled and the “Tap Record” instruction is
hidden. Next can prepare a new visit and enable recording again. The first
review remains frozen.

`DirectPracticeSession.canStartRecording` contains the former action's exact
guards: guided policy, startup availability, session availability, ready or
permission-denied phase, no retained takes, and the stored mirror's pending
camera-permission gate. `startRecording` and the ready view share this predicate.
Replacement recording, permission retry, cancellation, cleanup and model behavior
are unchanged. Evaluating eligibility does not construct a lazy mirror.

## Observed checks

Four methods passed once each in the optimized Release test host:

- The new controlled background regression holds the first word check and its
  exact file borrow. Inactive/background/active notifications cannot discard it
  before the receipt. A late matched result settles as cancelled, cleanup removes
  the take, and the still-open first visit cannot record or check again. Next
  preserves the first row and prepares the distinct pig visit with recording
  eligibility, without another recording or word check.
- Existing permission-denied retry remains available.
- Startup cleanup failure continues to withhold recording safely.
- A retained take remains protected through denied or failed replacement.

The existing camera-permission method passed once in a separate Debug test host.
Its fake permission and driver cover both grant/active scene orders: recording is
ineligible while permission is pending and eligible after the mirror becomes
ready. This is controlled Debug evidence; no physical camera or permission dialog
was tested.

The original Release selection mistakenly requested this fifth method even
though it is inside `#if DEBUG`. Only four methods executed. Its partial result
collection failed when requesting the missing camera detail. That failure and
the original five-name selection remain unchanged. The four passes were not
rerun. One previously uncollected detail for a passed Release method was read
separately, and the previously unexecuted camera method received its own Debug
build, compiler admission and one-method result.

The official summaries report four Release passes and one separate Debug pass,
with zero failures, skips, expected failures or runtime warnings in each actual
run, on the same arm64 iPhone SE (3rd generation), iOS 26.5 simulator. Raw Xcode
`invalidDigitCount` diagnostics remain in the saved logs.

## Restoration and limits

The ordinary Release app was built and checked separately: full production
sources, optimization, no DEBUG/testability/lifecycle/profiling conditions, exact
19 bundled Whisper resources and no verification fixtures or test plugins.
That same guarded prebuild was restored without launching after each test group;
the dedicated simulator returned to Shutdown. Signing and account settings were
unchanged, and no recordings were uploaded.

Evidence is kept in `work/mobile-word-background-20261017` and the separate
`work/mobile-camera-capability-20261017`. Exact prior source versions, frozen
inputs, compiler/source-list evidence, partial failure, distinct official reports,
parent-exit observations and independent reviews remain separate.

These tests use controlled capture and recognition. They do not verify pressing
Home during real model work, interruption inside Core ML, actual sensors,
performance or clinical validity. A separate Home/foreground host and UI test
have passed source review but have not been compiled or executed. The ordinary
browser app on port 8823, Apple authorization denial and consumed research study
were left unchanged.
