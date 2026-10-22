# Non-speech input boundary

The unchanged raw-WAV research adapter processed silence, Gaussian noise and
a 440 Hz tone without an error or semantic abstention. All four final heads
assigned silence their highest probability to corpus class 2. A valid audio
file, successful forced alignment and a finite rating distribution therefore
do not establish speech presence or pronunciation correctness.

This is the fixed three-input diagnostic in the
[protocol](multiphone-nonspeech-protocol.md), not training or an accuracy
benchmark. Each signal is exactly two seconds of mono 16 kHz PCM16. The same
explicit prompt, `BALL / B AO1 L`, requests target B. Noise and tone have
achieved RMS approximately 0.1 (−20 dBFS); silence has RMS zero. No signal
clips. The exact bytes, source, prompt, adapter and four unchanged final
manifests were declared before acoustic inference.

The existing adapter ran once per signal, on CPU with two threads and offline
weights. The resulting `[1,1037]` feature matrix was reused across all four
heads. First-head replay matched the adapter exactly in all three cases.
The run completed at 14:07:59 UTC on September 26, 2026, in 19.583 seconds.
No repeats, threshold search, fitting, reference-rating transfer or model
selection occurred.

| Generated input | Unweighted all-age P(class 2) | Unweighted child P(class 2) | Weighted all-age P(class 2) | Weighted child P(class 2) |
| --- | ---: | ---: | ---: | ---: |
| Silence | 0.885483 | 0.879436 | 0.918998 | 0.674698 |
| Gaussian noise | 0.878062 | 0.741721 | 0.888969 | 0.460449 |
| 440 Hz tone | 0.494925 | 0.884486 | 0.514099 | 0.492857 |

These are raw **corpus-rating probabilities**, not probabilities of a correct
sound. The complete three-class outputs are retained in the
[actual report](../../research/audio-head/outputs/multiphone-20260926/nonspeech-boundary-v1/results/report.json).
All three recordings have zero greedy CTC tokens. Forced alignment still
assigns the requested B one frame, where B is not the recognizer's argmax.
This describes the existing pipeline; it supplies no validated rejection rule.

The native demo does not consume these scores. Its recording-level and length
tips are not speech detection. Before connecting research output to learner
judgments, evaluate speech/prompt presence and abstention with representative
child speech, genuine errors and nonspeech negatives, separately from sound
correctness. A new cutoff chosen from these three signals would not establish
that capability. The diagnostic changes neither the model exports nor app
feedback.

The declaration SHA-256 is
`7f8bd3a7175b1e5a43dbd802637ae7f9ddde8064ca49f7e57eab8589cb625470`;
the actual report SHA-256 is
`0af3245208602f10291c2759723ec9a9526a371399f978912eef422f77ef82cf`.
Four synthetic tests cover exact signals, declaration changes, feature reuse
and error-versus-abstention handling. Both the implementation and declaration
passed separate review before actual inference.

Two saved-artifact audits subsequently passed without repeating inference.
The independent review checked 180 input-pin entries and 15 derived artifacts
across 81 distinct paths, regenerated all three PCM arrays, reconstructed CTC
paths and recording measurements, and checked all 12 distributions and exact
feature reuse. The absence of a speech-presence policy remains a measured
limitation; no rejection rule was added.
