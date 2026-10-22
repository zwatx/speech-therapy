# Fixed non-speech research boundary diagnostic

This diagnostic measures a missing input boundary of the existing research WAV
adapter. It does not fit models, label pronunciation, set rejection thresholds,
or change the native app. A valid WAV and a requested canonical prompt do not
establish that speech was recorded. Existing recording measurements do not
implement speech-presence detection or semantic abstention.

Declare exactly three two-second mono 16 kHz PCM16 signals before inference:

- All-zero samples.
- NumPy PCG64 seed 20260926 Gaussian samples, normalized once in float64 to RMS
  0.1 before PCM quantization.
- A zero-phase 440 Hz sine, amplitude `sqrt(2) * 0.1`, generated in float64.

Quantize once by rounding `x * 32768` to nearest-even signed PCM16. Reject any
out-of-range samples rather than clipping. Record achieved RMS, peaks, bytes and
hashes; quantization can slightly change RMS. Use the same explicit prompt for
all signals: `BALL`, canonical `B AO1 L`, target `B` at word 0 / phone 0.
There are no human rating labels on these generated waveforms.

Pin this protocol, the diagnostic source, unchanged adapter/feature/runtime
sources, exact offline checkpoints, signal and prompt bytes, completed final
export ledger and all four unchanged final manifests before acoustic inference.
The declaration creates no model predictions. The subsequent fresh run invokes
the existing raw adapter exactly once per waveform, using the unweighted
all-age bundle. Reuse that exact saved float32 `[1,1037]` feature matrix with the
unchanged portable loader for the other three final heads; require exact parity
between the adapter's first-head probabilities and feature-level replay.
Use CPU with two threads, pinned offline extraction, no MPS, no downloads.

Retain every pipeline acceptance or error, CTC and forced-path diagnostics,
feature hashes and finite/shape checks, separate recording levels, and raw
three-class corpus-vote probabilities from all four bundles. Distinguish a
runtime or contract error from semantic abstention: the existing adapter has
no speech detector or abstention policy. Do not infer speech presence from
forced alignment, a finite feature vector, a high class-2 probability, or an
acceptable level/duration. No repeats, alternate seeds, extra prompts, model
selection, accuracy calculation, thresholds, calibration, or learner feedback.
This is three deterministic failure-case observations, not an out-of-domain
benchmark or a validated rejection policy.
