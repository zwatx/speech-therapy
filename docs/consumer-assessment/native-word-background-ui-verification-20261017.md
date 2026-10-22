# Returning to guided practice during a word check

One simulator UI journey passed using the production guided-practice view and a
real bundled recognition worker. After checking a public example of “bread,” the
test pressed Home and returned to the same app session. The app showed
“Cancelling word check. Waiting for the recognizer to finish cleanup…” while the
original recording remained protected. It waited for the real worker's cleanup
receipt before the recording's producer discarded the file.

The cancelled first review stayed frozen and open. Record was disabled, the
“Tap Record” instruction was absent, and Next remained available. Pressing Next
prepared a distinct “pig” visit in the same round with recording enabled. No
second recording or recognition request occurred. Only afterward did the test
press Close and observe the production flow close and its cover disappear.

## Observed evidence

The official result contains exactly one passing method, one run and one
configuration on the dedicated arm64 iPhone SE (3rd generation), iOS 26.5
simulator. The method took 31.846 seconds. The official summary reports zero
failures, skips, expected failures or runtime warnings. Raw logs retain Xcode's
`invalidDigitCount` and duplicate accessibility-class diagnostics.

The saved 6,669-byte JSON attachment records 27 ordered events: 24 distinct
milestones and three cancellation requests, all for the original operation.
Inactive, background and active scene observations occur between the held
encoder result and the foreground pending checkpoint. The original app-session
nonce, take, operation, file identity and file hash agree throughout. No receipt,
discard or close occurred while the worker still held the recording.

A labeled test-only button released the encoder hold about 6.724 seconds after
it began. The real worker then returned cancelled with cleanup confirmed and no
retained handle; its receipt preceded the producer's single discard. There were
no safety releases, history rows or remaining ownership/recovery entries. The
recognizer deadline and gate limit remained 15 seconds, including time spent
in the background. This is a deliberate hold after the encoder returns, not an
interruption inside a Core ML prediction.

The actual activity log contains one Start, Record, Stop, Check, Home, activation,
release, Next and Close in that order. Independent UI assertions also check the
pending text, disabled first-visit Record control and ready successor. No
screenshots were collected; this checkpoint makes no visual-layout claim.

## Build, restoration and scope

The generated verification host uses the production view, coordinator, temporary
recording store and recognition worker. Capture hardware and its permission are
controlled substitutes that copy one attributed public audio fixture. No
microphone, camera, playback, participant recording or upload was used. One
worker entry and encoder return are observed; two model constructions and zero
decoder predictions are source-derived counts.

Both verification and ordinary app builds passed separate compiler/source-list
and resource checks. The ordinary app contains the full production sources,
optimized Release settings, exact 19 bundled Whisper resources and no test
fixtures, test plugins, DEBUG, testability, lifecycle or profiling conditions.
That same ordinary prebuild was installed afterward without launching. The
dedicated simulator returned to Shutdown. Signing and account settings were
unchanged.

Saved evidence is in `work/mobile-word-background-ui-20261017`: reviewed host and
UI sources, frozen inputs, compiler admissions, official reports and attachment,
raw activity log, parent-exit observations, restoration receipts and independent
reviews. The model-backed journey ran once; saved-result reconciliation does
not rerun recognition.

This verifies returning to the production practice view during a deliberately
held word check. It does not establish responsiveness during model loading or
prediction, standalone Cancel, ordinary recognition latency, physical-device
behavior, a fresh successor recording, individual-sound accuracy or clinical
diagnosis. Apple English speech assets remain ready; Apple Speech authorization
was previously denied before recognition. No reset or unchanged retry occurred.
The whole-app goal remains active.
