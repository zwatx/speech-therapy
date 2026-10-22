# Frozen speech-detector short-word sensitivity check

Declared September 27, 2026 after the full-recording VAD study and before any
VAD inference on these crops. Use every one of the 17 previously saved word
crops in the September 26 word-context diagnostic, covering 23 target positions
and 16 consonants from five children ages 6, 8, 10, 11 and 12. No selection,
recropping, padding change, duration filtering or replacement is allowed.

Bind the existing diagnostic report SHA-256
`6b3df8d70231cd2ee23f3c79dfb645524d5ad94ff4167f8e8a446de4a21b219e`.
Verify each exact crop waveform and its original sample slice before inference.
Use the same Silero model, source, settings and CPU runtime as VAD-v1, whose
report SHA-256 is
`e343ea03db257fbffd28fa10da8811d7e53e4ef5328842379d32fb4699b9b8c5`.
That study retained all five original full recordings. Reuse those bound
original decisions; do not perform another full-recording inference.

Compute the fixed phone-evidence gate on each crop's existing bound full392
CTC posterior, then the fixed Silero candidate on the unchanged crop waveform.
Report both decisions and their conjunction for every crop, including duration,
original speaker/age, target phones and full-recording decision. Do not transfer
the original rating labels to the crops or measure pronunciation correctness.

Write and hash a complete plan before inference, binding all relevant sources,
artifacts, waveforms and settings. Use a fresh output directory. Save every
probability and timestamp; fail on integrity/runtime errors rather than count
them as rejections. Separately reconstruct all intervals and decisions from
saved probabilities, verify all hashes and report exact 17-word/23-position
coverage. Reuse the already tested state-reset/inference helpers unchanged.

The crops span estimated canonical word emissions plus 100 ms at each side and
are 0.285–0.645 seconds long. They are not validated word boundaries or natural
isolated-word recordings. Rejection may reflect truncation, loss of context,
model behavior or the fixed duration requirement. Acceptance does not prove
correct articulation. No threshold adjustment, fitting or product integration
follows from the results. Learner judgments remain disabled.
