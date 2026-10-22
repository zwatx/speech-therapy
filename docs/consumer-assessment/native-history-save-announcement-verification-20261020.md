# History-save accessibility announcements — October 20

The player previously announced a successful save retry but did not announce a
failed save. Repeated failures could keep identical visible text without supplying
another spoken status update.

Each accepted save outcome now creates a distinct, completion-bound announcement
event. Ordinary initial success says “Practice complete.” Initial failure uses
the existing combined completion/error message. Each explicit retry reports its
failure or success. Guided initial success stays quiet. The player has one guarded
observer, with no initial replay or focus change. Revoked completions cannot supply
a current event, including revocation during synchronous store/note/event publication.
Visible messages, participation IDs/counts and media ownership are preserved.

## Observed verification

- Corrected V2: all thirteen exact selected native unit methods passed on the
  dedicated iPhone SE (3rd generation), iOS 26.5 simulator. No tests were skipped
  or expected to fail; the official runtime-warning list was empty.
- The tests cover ordinary/guided completion, repeated identical failed retries,
  successful and rejected retries, unavailable storage, restart/more/Close,
  synchronous revocation and unchanged saved identity/audio-operation counts.
  Capture, playback and recognition use existing fakes with isolated temporary stores.
- A fresh ordinary optimized Release build passed its four compiler-group checks.
  Installation completed normally; all twenty-six installed relative files/bytes,
  including nineteen existing resources, matched the admitted build.
  The simulator finished Shutdown. Ordinary app Data was not inspected or reset.
- V1 remains twelve passed and one failed. Its new test wrongly expected one
  total capture after five generated seed captures plus one practice capture.
  V2 asserts the exact seed count and one additional practice capture; the same
  thirteen methods, other assertions and execution limits remain.

## Limits and evidence

These checks verify source-event behavior and compilation, not actual VoiceOver
audibility, scheduling or interruption quality. V1 logged duplicate Apple
accessibility classes and other system diagnostics despite an empty official
warning list. V2 retained SDK build-record diagnostics; the absence of the other
messages in V2 does not establish that their cause was resolved. No OS repair,
warning suppression, live capture, model evaluation or clinical qualification occurred.

One observation-order deviation is retained: the pure Release admission process
was still reported live when installation was dispatched. The installer required
its completed admission artifact and repeated the build/product checks. Both
parents subsequently terminated with exit 0, and the separate installed-byte
comparison passed. No claim is made that Root observed admission termination
before dispatching installation.

Exact sources, reviews, original failure, corrected test delta, parent observations,
official results and installed comparison are retained under
`work/history-save-announcements-20261020/`. No Git publication was performed.
