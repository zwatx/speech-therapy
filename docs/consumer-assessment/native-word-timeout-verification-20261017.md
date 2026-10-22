# Distinct word-check timeout feedback

A word-check deadline now produces a distinct timeout outcome. The kept take says
“Word check took too long. You can still record and listen.” Guided first-review
context and summaries retain “Word check took too long.” A completed unclear
recognition still says “No clear match.” The message remains tied to the exact
checked take.

The existing 15-second cooperative deadline, cancellation priority, worker/timer
joins and recording protection are unchanged. A deadline does not release a
recording or promise immediate interruption of Core ML. Same-take retry is not
expanded; explicit replay, replacement recording, manual practice and safe guided
progress remain available. A timeout cannot trigger research-model readiness or
processing, and a later recheck cannot replace the frozen first-review result.

Actual verification passed **21 selected tests, once each, with no failures,
skips or expected failures**, on the dedicated iPhone SE simulator running iOS
26.5. The official result tree and raw start/pass records match the fixed
selection. These use generated recordings and controlled worker/recorder/player
seams, including a late matched result after a signaled deadline, cancellation,
failed cleanup, exact-take presentation, frozen review/recheck, model suppression
and continued replay/replacement/Close/manual progression. They do not measure
live model latency or a real 15-second wall-clock timeout.

The complete Debug test target compiled successfully. A fresh optimized Release
app also compiled, retained the unchanged 19 ordinary Whisper resource files,
and was installed before the simulator returned to Shutdown. Actual app/contracts
compiler inputs cover arm64 and x86_64, Swift 6 and optimization, without DEBUG,
testability or the hidden-model lifecycle hook. The canonical scheme still adds
profiling instrumentation to that Release build; this is not a performance
measurement or a claim of an uninstrumented shipping build. No ordinary UI launch
or normal/largest-text timeout screenshot was taken in this checkpoint.

Two earlier builds exposed missing timeout cases in private diagnostic test
utilities. A subsequent test launch rejected a redundant iteration option before
any test ran. Those failures remain preserved; the utilities and command were
corrected before the first actual execution of the 21 selected cases.

Evidence and the independent [actual-result review](../../work/mobile-word-timeout-20261017/execution-v4/RESULT-REVIEW.md)
are retained under `work/mobile-word-timeout-20261017/`. The original substantive
[source review](../../work/mobile-word-timeout-20261017/SOURCE-REVIEW.md) and the
[official admission](../../work/mobile-word-timeout-20261017/execution-v4/OFFICIAL-ADMISSION.json)
identify the covered behaviors and current source.

Apple's previously installed English assets and on-device capability remain
separate from its unresolved authorization denial. No Apple recognition retry,
permission reset, signing/account change, live capture or recording upload occurred.
Bundled word recognition remains the working route. Individual-sound correction,
diagnosis and the complete native assessment pipeline remain unqualified.
